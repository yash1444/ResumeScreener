import asyncio
from pathlib import Path

import pytest

import samples as S
from resume_screener import config as cfg
from resume_screener.config import Settings
from resume_screener.eligibility import check_eligibility, work_blocks
from resume_screener.extraction import build_profile, extract_github
from resume_screener.github_client import GitHubEnricher
from resume_screener.ingestion import ingest_folder
from resume_screener.models import RawResume
from resume_screener.pipeline import run_pipeline
from resume_screener.scoring import rule_score

SETTINGS = Settings(openai_api_key=None, github_token=None)


def analyse(text: str):
    profile = build_profile(RawResume(path="x", filename="x.txt", text=text))
    blocks = work_blocks(profile)
    elig = check_eligibility(profile, blocks, SETTINGS)
    return profile, blocks, elig


# ----------------------------------------------------------------- eligibility
def test_strong_candidate_is_eligible():
    _, _, e = analyse(S.STRONG)
    assert e.eligible and e.ai_evidence_level == "llm_agentic" and e.python_evidence


def test_js_only_is_rejected_with_both_reasons():
    _, _, e = analyse(S.JS_ONLY)
    assert not e.eligible
    assert "No evidence of Python stack" in e.rejection_reasons
    assert any("AI/agentic" in r for r in e.rejection_reasons)
    assert "React" in e.matched_skills


def test_python_without_ai_is_rejected():
    _, _, e = analyse(S.PYTHON_NO_AI)
    assert not e.eligible and e.python_evidence
    assert e.rejection_reasons == ["No AI/agentic project evidence"]


def test_ai_keywords_only_in_skills_list_do_not_qualify():
    _, _, e = analyse(S.SKILLS_ONLY_AI)
    assert not e.eligible
    assert "skills" in e.rejection_reasons[0]


def test_js_langchain_profile_has_no_python_evidence():
    _, _, e = analyse(S.JS_LANGCHAIN_ONLY)
    assert not e.eligible and "No evidence of Python stack" in e.rejection_reasons


def test_js_alongside_python_and_ai_is_fine():
    text = S.STRONG.replace("Python, FastAPI", "JavaScript, React, Python, FastAPI")
    _, _, e = analyse(text)
    assert e.eligible


# ----------------------------------------------------------------- scoring
def test_strong_scores_high_and_within_caps():
    p, b, e = analyse(S.STRONG)
    rs = rule_score(p, b, e.ai_evidence_level)
    assert rs.ai_project_depth >= 28 and rs.penalty == 0
    assert rs.python_backend >= 20
    assert rs.ai_project_depth <= cfg.WEIGHTS["ai_project_depth"]
    assert rs.python_backend <= cfg.WEIGHTS["python_backend"]
    assert rs.cloud_fullstack <= cfg.WEIGHTS["cloud_fullstack"]
    assert rs.engineering_depth <= cfg.WEIGHTS["engineering_depth"]


def test_thin_wrapper_is_penalised_and_ranks_below_strong():
    ps, bs, es = analyse(S.STRONG)
    pt, bt, et = analyse(S.THIN_WRAPPER)
    assert et.eligible
    strong, thin = rule_score(ps, bs, es.ai_evidence_level), rule_score(pt, bt, et.ai_evidence_level)
    assert thin.penalty >= cfg.PENALTY_SOME_THIN and thin.penalty_reasons
    assert thin.ai_project_depth < strong.ai_project_depth - 15


# ----------------------------------------------------------------- extraction
def test_github_username_from_text_and_links_ignores_reserved_paths():
    assert extract_github("see github.com/features and github.com/asharao-dev/repo", [])[0] == "asharao-dev"
    assert extract_github("GitHub", ["https://github.com/someone"])[0] == "someone"
    assert extract_github("GitHub", ["https://github.com/"])[0] is None


# ----------------------------------------------------------------- ingestion / batch resilience
def test_bad_and_duplicate_files_do_not_crash_batch(tmp_path: Path):
    (tmp_path / "a.txt").write_text(S.STRONG)
    (tmp_path / "a_copy.txt").write_text(S.STRONG)  # duplicate content
    (tmp_path / "broken.pdf").write_bytes(b"%PDF-1.4 not really a pdf")
    (tmp_path / "empty.txt").write_text("")
    (tmp_path / "b.txt").write_text(S.JS_ONLY)
    (tmp_path / "ignore.png").write_bytes(b"\x89PNG")
    rep = ingest_folder(tmp_path)
    assert len(rep.resumes) == 2
    assert {f["filename"] for f in rep.failed} == {"broken.pdf", "empty.txt"}
    assert rep.duplicates and rep.duplicates[0]["duplicate_of"] == "a.txt"

    out = run_pipeline(tmp_path, SETTINGS, analyzer=None)
    s = out["batch_summary"]
    assert (s["total_resumes"], s["successfully_parsed"], s["eligible"], s["rejected"], s["failed_or_unreadable"]) == (5, 2, 1, 1, 2)
    assert out["ranked_candidates"][0]["rank"] == 1


def test_llm_failure_falls_back_to_rules(tmp_path: Path):
    class Boom:
        async def analyze(self, *_):
            raise RuntimeError("model down")

    (tmp_path / "a.txt").write_text(S.STRONG)
    out = run_pipeline(tmp_path, SETTINGS, analyzer=Boom())
    top = out["ranked_candidates"][0]
    assert top["scoring_method"] == "rules" and any("LLM analysis failed" in n for n in top["notes"])


# ----------------------------------------------------------------- GitHub resilience
def test_github_rate_limit_is_recorded_not_raised(monkeypatch):
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "rate limit"}, headers={"x-ratelimit-remaining": "0"})

    async def go():
        gh = GitHubEnricher(None)
        gh._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com")
        gh._disk = {}
        r1 = await gh.enrich("someone")
        r2 = await gh.enrich("someone")  # cached: no second request
        await gh._client.aclose()
        return r1, r2

    r1, r2 = asyncio.run(go())
    assert r1.status == "rate_limited" and r1.score == 0 and r2 is r1


# ----------------------------------------------------------------- borderline detection + LLM second opinion
from resume_screener.models import EligibilityOpinion  # noqa: E402


class FakeAnalyzer:
    """analyze() always fails (so rule scores are used); second_opinion() returns a canned answer or raises."""

    def __init__(self, python=True, builds=True, boom=False):
        self.python, self.builds, self.boom, self.calls = python, builds, boom, 0

    async def analyze(self, *_):
        raise RuntimeError("analysis unavailable")

    async def second_opinion(self, text, reasons):
        self.calls += 1
        if self.boom:
            raise RuntimeError("model down")
        return EligibilityOpinion(
            python_is_genuine=self.python, python_evidence="x", builds_with_llm_or_agents=self.builds,
            ai_evidence="y", confidence="medium", reasoning="canned opinion",
        )


def test_clear_cut_resumes_are_not_borderline():
    assert analyse(S.STRONG)[2].borderline_reasons == []
    assert analyse(S.JS_ONLY)[2].borderline_reasons == []


def test_thin_ai_evidence_and_skills_only_python_are_borderline():
    assert "ai_evidence_is_thin" in analyse(S.THIN_WRAPPER)[2].borderline_reasons
    e = analyse(S.PYTHON_IN_SKILLS_ONLY)[2]
    assert e.eligible and "python_only_in_skills_list" in e.borderline_reasons


def test_rejected_near_miss_is_borderline():
    e = analyse(S.SKILLS_ONLY_AI)[2]
    assert not e.eligible and e.borderline_reasons == ["ai_keywords_only_in_skills_or_summary"]


def _screen(tmp_path, text, analyzer, **settings):
    (tmp_path / "a.txt").write_text(text)
    return run_pipeline(tmp_path, Settings(openai_api_key=None, github_token=None, **settings), analyzer=analyzer)


def test_disagreeing_opinion_flags_review_but_never_changes_the_rule_decision(tmp_path: Path):
    out = _screen(tmp_path, S.SKILLS_ONLY_AI, FakeAnalyzer(python=True, builds=True))  # LLM says "qualifies"
    assert out["batch_summary"]["eligible"] == 0 and out["batch_summary"]["rejected"] == 1  # rules still win
    rej = out["rejected_candidates"][0]
    assert rej["eligibility_check"]["needs_human_review"] is True and rej["eligibility_check"]["final_decision"] == "rejected"
    assert out["batch_summary"]["needs_human_review"] == 1 and out["needs_human_review"][0]["rules_decision"] == "rejected"


def test_agreeing_opinion_is_recorded_without_review_flag(tmp_path: Path):
    out = _screen(tmp_path, S.THIN_WRAPPER, FakeAnalyzer(python=True, builds=True))
    chk = out["ranked_candidates"][0]["eligibility_check"]
    assert chk["llm_agrees"] is True and chk["needs_human_review"] is False
    assert out["batch_summary"]["second_opinions_obtained"] == 1


def test_opinion_that_rejects_an_eligible_candidate_only_flags_it(tmp_path: Path):
    out = _screen(tmp_path, S.THIN_WRAPPER, FakeAnalyzer(python=True, builds=False))
    top = out["ranked_candidates"][0]
    assert top["eligible"] and top["eligibility_check"]["needs_human_review"] is True
    assert top["concerns"][0].startswith("Eligibility flagged for human review")


def test_second_opinion_failure_or_opt_out_keeps_rule_decision(tmp_path: Path):
    out = _screen(tmp_path, S.THIN_WRAPPER, FakeAnalyzer(boom=True))
    chk = out["ranked_candidates"][0]["eligibility_check"]
    assert chk["llm_second_opinion"] is None and "second_opinion_error" in chk and out["batch_summary"]["eligible"] == 1
    fake = FakeAnalyzer()
    out2 = _screen(tmp_path, S.THIN_WRAPPER, fake, second_opinion_enabled=False)
    assert fake.calls == 0 and out2["batch_summary"]["second_opinions_obtained"] == 0


# ----------------------------------------------------------------- keywords.yaml
def test_keywords_yaml_is_validated(tmp_path: Path):
    from resume_screener.keywords import KeywordConfigError, load_keywords

    assert load_keywords()["ai_anchors"]  # shipped file is valid
    good = (Path(__file__).parent.parent / "src" / "resume_screener" / "keywords.yaml").read_text(encoding="utf-8")
    bad_regex = tmp_path / "bad.yaml"
    bad_regex.write_text(good.replace("'scikit-?learn'", "'(unclosed'", 1), encoding="utf-8")
    with pytest.raises(KeywordConfigError, match="invalid regex"):
        load_keywords(bad_regex)
    missing = tmp_path / "missing.yaml"
    missing.write_text(good.replace("python_explicit:", "python_explicit_renamed:", 1), encoding="utf-8")
    with pytest.raises(KeywordConfigError, match="missing section"):
        load_keywords(missing)


# ----------------------------------------------------------------- output format (assignment section 7 / section 3)
def test_spec_list_and_candidate_alias(tmp_path: Path):
    from resume_screener.pipeline import SPEC_KEYS, to_spec_list

    (tmp_path / "a.txt").write_text(S.STRONG)
    (tmp_path / "b.txt").write_text(S.JS_ONLY)
    out = run_pipeline(tmp_path, SETTINGS, analyzer=None)
    spec = to_spec_list(out)
    assert isinstance(spec, list) and len(spec) == 1
    assert list(spec[0]) == list(SPEC_KEYS) and spec[0]["rank"] == 1
    assert list(spec[0]["score_breakdown"]) == ["ai_project_depth", "python_backend", "cloud_fullstack", "github", "engineering_depth"]
    rej = out["rejected_candidates"][0]
    assert rej["candidate"] == rej["candidate_name"] and rej["eligible"] is False and rej["rejection_reasons"]


# ----------------------------------------------------------------- claim-vs-proof (resume claims vs GitHub repos)
from resume_screener.claim_check import RepoRef, claimed_techs, judge, select_repos, verify_claims  # noqa: E402


def _blocks(text):
    p = build_profile(RawResume(path="x", filename="x.txt", text=text))
    return p, work_blocks(p)


class FakeGH:
    def __init__(self, repos, evidence):
        self.repos, self.evidence, self.asked = repos, evidence, []

    async def list_repos(self, username):
        return self.repos

    async def repo_evidence(self, owner, name):
        self.asked.append(f"{owner}/{name}")
        return self.evidence.get(name)


def test_claims_come_from_project_text_not_skills_list():
    _, blocks = _blocks(S.STRONG)
    claims = claimed_techs(blocks)
    assert "LangGraph" in claims and "Docker" in claims and "Redis" in claims
    only_skills = S.SKILLS_ONLY_AI  # LangChain / RAG only appear in the skills list
    assert "LangChain" not in claimed_techs(_blocks(only_skills)[1])


def test_repo_selection_prefers_linked_then_name_match_and_caps_at_three():
    _, blocks = _blocks(S.STRONG)
    repos = [{"name": "stateful-research-agent", "fork": False, "pushed_at": "2026-01-01T00:00:00Z", "relevant": True},
             {"name": "dotfiles", "fork": False, "pushed_at": "2026-02-01T00:00:00Z", "relevant": False},
             {"name": "rag-demo", "fork": False, "pushed_at": "2026-03-01T00:00:00Z", "relevant": True},
             {"name": "agent-x", "fork": False, "pushed_at": "2026-04-01T00:00:00Z", "relevant": True},
             {"name": "llm-y", "fork": False, "pushed_at": "2026-05-01T00:00:00Z", "relevant": True}]
    refs = select_repos("asharao-dev", ["https://github.com/asharao-dev/special-repo"], blocks, repos)
    assert refs[0] == RepoRef("asharao-dev", "special-repo", "linked_in_resume")
    assert refs[1].source == "name_match" and refs[1].name == "stateful-research-agent"
    assert len(refs) == 3 and "dotfiles" not in [r.name for r in refs]


def test_judge_verifies_claims_in_real_repos_and_ignores_forks():
    claims = ["LangGraph", "FastAPI", "Docker", "Redis"]
    good = {"fork": False, "has_readme": True, "active_span_days": 40, "text": "uses langgraph and fastapi, run with docker compose"}
    forked = {"fork": True, "has_readme": True, "active_span_days": 40, "text": "redis langgraph fastapi docker"}
    rep = judge(claims, [(RepoRef("a", "r1", "linked_in_resume"), good), (RepoRef("a", "r2", "name_match"), forked)])
    assert rep["verified_techs"] == ["Docker", "FastAPI", "LangGraph"] and rep["unverified_techs"] == ["Redis"]
    assert rep["score_bonus"] == 2 and rep["repos_checked"][1]["claimed_techs_found"] == []  # fork proves nothing
    only_fork = judge(claims, [(RepoRef("a", "r2", "name_match"), forked)])
    assert only_fork["score_bonus"] == 0 and only_fork["claims_verified"] == 0
    one_day_upload = judge(claims, [(RepoRef("a", "r1", "linked_in_resume"), dict(good, active_span_days=0))])
    assert one_day_upload["score_bonus"] == 0  # a single-day dump earns no bonus


def test_verify_claims_is_failure_tolerant_and_skips_without_proof():
    _, blocks = _blocks(S.STRONG)

    class Broken(FakeGH):
        async def list_repos(self, username):
            raise RuntimeError("boom")

    assert asyncio.run(verify_claims("u", [], blocks, Broken([], {})))["status"] == "error"
    assert asyncio.run(verify_claims(None, [], blocks, FakeGH([], {}))) is None
    repos = [{"name": "stateful-research-agent", "fork": False, "pushed_at": "2026-01-01T00:00:00Z", "relevant": True}]
    out = asyncio.run(verify_claims("u", [], blocks, FakeGH(repos, {})))  # repo exists but contents unavailable
    assert out["status"] == "skipped" and out["score_bonus"] == 0


# ----------------------------------------------------------------- deeper claim scan (subfolders + file names) and disclosure
def test_manifest_paths_include_subfolders_but_skip_vendored_dirs():
    from resume_screener.github_client import paths_to_text, pick_manifest_paths

    paths = ["README.md", "backend/requirements.txt", "frontend/package.json", "node_modules/x/package.json",
             "a/b/c/d/requirements.txt", "docs/notes.md", "venv/lib/requirements.txt", "package.json", "build/app.py"]
    got = pick_manifest_paths(paths)
    assert got == ["package.json", "backend/requirements.txt", "frontend/package.json"]  # shallow first; deep + vendored skipped
    text = paths_to_text(["CrewAI_Agents/app.py", "RAG_Embeddings/store.py", "node_modules/x/y.js"])
    assert "CrewAI Agents" in text and "RAG Embeddings" in text and "node modules" not in text.lower()


def test_judge_reports_where_each_claim_was_found_and_discloses_its_scope():
    claims = ["CrewAI", "RAG", "FastAPI", "Redis"]
    ev = {"fork": False, "has_readme": False, "active_span_days": 30, "files_listed": 12,
          "manifests_read": ["backend/requirements.txt"],
          "sources": {"file names": "CrewAI Agents RAG Embeddings app py", "backend/requirements.txt": "fastapi==0.1\nuvicorn"}}
    rep = judge(claims, [(RepoRef("u", "r", "name_match"), ev)])
    assert rep["verified_in"] == {"CrewAI": "u/r: file names", "RAG": "u/r: file names", "FastAPI": "u/r: backend/requirements.txt"}
    assert rep["unverified_techs"] == ["Redis"] and rep["score_bonus"] == 2
    assert "does not mean the claim is false" in rep["summary"]
    assert "none of the checked repos has a README" in rep["summary"]
    assert "NOT scanned" in rep["check_scope"]
