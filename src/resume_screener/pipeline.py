"""Orchestrates: ingest -> extract -> eligibility -> score (rules + LLM) -> GitHub -> rank."""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from . import config as cfg
from .config import Settings
from .eligibility import check_eligibility, work_blocks
from .extraction import build_profile
from .claim_check import verify_claims
from .github_client import GitHubEnricher
from .ingestion import IngestionReport, ingest_folder
from .llm import ResumeAnalyzer, build_analyzer, safe_analyze, safe_second_opinion
from .models import CandidateProfile, CandidateResult, GitHubResult, LLMAnalysis, ScoreBreakdown
from .scoring import RuleScores, rule_score

log = logging.getLogger(__name__)


def _clamp(llm_value: int, base: int, delta: int, maximum: int) -> int:
    return max(0, min(maximum, max(base - delta, min(base + delta, llm_value))))


def blend(rs: RuleScores, llm: LLMAnalysis | None) -> tuple[ScoreBreakdown, int, list[str], list[str]]:
    """Combine rule scores with the (bounded) LLM judgement. Returns breakdown, penalty, penalty notes, notes."""
    w = cfg.WEIGHTS
    notes: list[str] = []
    if llm is None:
        b = ScoreBreakdown(
            ai_project_depth=rs.ai_project_depth, python_backend=rs.python_backend,
            cloud_fullstack=rs.cloud_fullstack, engineering_depth=rs.engineering_depth,
        )
        return b, rs.penalty, rs.penalty_reasons, notes
    d = cfg.LLM_MAX_DELTA
    ai_raw = _clamp(llm.ai_project_depth.score, rs.ai_before_penalty, d["ai_project_depth"], w["ai_project_depth"])
    penalty = rs.penalty
    penalty_notes = list(rs.penalty_reasons)
    if llm.penalty or llm.thin_wrapper_projects or llm.tutorial_style_projects:
        penalty = min(cfg.PENALTY_MAX, round((rs.penalty + llm.penalty) / 2)) if rs.penalty else min(cfg.PENALTY_MAX, llm.penalty)
        flagged = llm.thin_wrapper_projects + llm.tutorial_style_projects
        if flagged:
            penalty_notes.append("LLM flagged shallow projects: " + "; ".join(flagged[:3]))
    elif rs.penalty and not llm.thin_wrapper_projects:
        penalty = rs.penalty // 2  # the model saw no shallow projects: soften the rule-based penalty
        notes.append("LLM did not confirm shallow-project penalty; halved")
    b = ScoreBreakdown(
        ai_project_depth=max(0, ai_raw - penalty),
        python_backend=_clamp(llm.python_backend.score, rs.python_backend, d["python_backend"], w["python_backend"]),
        cloud_fullstack=_clamp(llm.cloud_fullstack.score, rs.cloud_fullstack, d["cloud_fullstack"], w["cloud_fullstack"]),
        engineering_depth=_clamp(llm.engineering_depth.score, rs.engineering_depth, d["engineering_depth"], w["engineering_depth"]),
    )
    return b, penalty, penalty_notes, notes


async def _process_one(
    raw, settings: Settings, analyzer: ResumeAnalyzer | None, llm_sem: asyncio.Semaphore, gh: GitHubEnricher
) -> CandidateResult:
    profile: CandidateProfile = build_profile(raw)
    blocks = work_blocks(profile)
    elig = check_eligibility(profile, blocks, settings)

    # GitHub + LLM run concurrently; neither can fail the candidate.
    gh_task = asyncio.create_task(gh.enrich(profile.github_username))
    rs = rule_score(profile, blocks, elig.ai_evidence_level) if elig.eligible else None
    llm_task = None
    if elig.eligible or analyzer is not None:
        hint = _hint(profile, elig, rs)
        llm_task = asyncio.create_task(safe_analyze(analyzer, llm_sem, profile.raw_text, hint))
    so_task = None
    if elig.borderline_reasons and settings.second_opinion_enabled and analyzer is not None:
        so_task = asyncio.create_task(safe_second_opinion(analyzer, llm_sem, profile.raw_text, elig.borderline_reasons))
    github: GitHubResult = await gh_task
    llm, llm_err = await llm_task if llm_task else (None, None)
    opinion, so_err = await so_task if so_task else (None, None)
    check = _eligibility_check(elig, opinion, so_err)

    name = profile.name
    if llm and llm.candidate_name and _name_is_weak(profile):
        name = llm.candidate_name.strip()

    if not elig.eligible:
        return CandidateResult(
            candidate_name=name, filename=profile.filename, email=profile.email, eligible=False,
            rejection_reasons=elig.rejection_reasons, matched_skills=profile.skills,
            github_summary=github.summary if github.username else "", github=github if github.username else None,
            project_summary=llm.project_summary if llm else "",
            eligibility_check=check,
            evidence={"eligibility_python": elig.python_evidence, "eligibility_ai": elig.ai_evidence},
            notes=["rejected by rule-based filter (the LLM can only flag borderline cases for review)"]
            + (["LLM second opinion disagrees with the rejection: review manually"] if check and check["needs_human_review"] else []),
        )

    assert rs is not None
    breakdown, penalty, penalty_notes, notes = blend(rs, llm)
    claim = await verify_claims(profile.github_username, raw.links, blocks, gh) if github.status in ("ok", "partial") else None
    if claim and claim.get("score_bonus"):
        breakdown.ai_project_depth = min(cfg.WEIGHTS["ai_project_depth"], breakdown.ai_project_depth + claim["score_bonus"])
    breakdown.github = min(cfg.WEIGHTS["github"], github.score)
    total = (breakdown.ai_project_depth + breakdown.python_backend + breakdown.cloud_fullstack
             + breakdown.github + breakdown.engineering_depth)
    notes = list(notes)
    if llm_err and llm_err != "llm_disabled":
        notes.append(f"LLM analysis failed, rule-based scores used: {llm_err}")
    if github.status not in ("ok", "no_profile"):
        notes.append(f"GitHub enrichment: {github.status} - {github.detail}")
    if profile.reordered:
        notes.append("PDF text blocks were stored out of order; text was re-ordered by page position")

    strengths = list(llm.strengths) if llm else _rule_strengths(rs, elig)
    concerns = list(llm.concerns) if llm else _rule_concerns(rs, elig, profile)
    if elig.ai_evidence_level == "classical_ml":
        concerns.append("AI evidence is classical ML/CV only (no LLM/RAG/agentic project)")
    if check and check["needs_human_review"]:
        concerns.insert(0, "Eligibility flagged for human review: LLM second opinion disagrees with the rule-based pass")
        notes.append("LLM second opinion disagrees with the eligibility decision: " + check["llm_second_opinion"]["reasoning"])
    summary = llm.project_summary if llm else (rs.ai_projects[0] if rs.ai_projects else (elig.ai_evidence[0] if elig.ai_evidence else ""))
    evidence = dict(rs.evidence)
    evidence["eligibility_python"] = elig.python_evidence
    evidence["eligibility_ai"] = elig.ai_evidence
    if llm:
        evidence["llm_ai_project_depth"] = llm.ai_project_depth.evidence
        evidence["llm_python_backend"] = llm.python_backend.evidence
        evidence["llm_cloud_fullstack"] = llm.cloud_fullstack.evidence
        evidence["llm_engineering_depth"] = llm.engineering_depth.evidence
    return CandidateResult(
        candidate_name=name, filename=profile.filename, email=profile.email, eligible=True,
        total_score=total, score_breakdown=breakdown, penalties=penalty_notes,
        matched_skills=profile.skills, project_summary=summary,
        github_summary=(github.summary + (f" Claim check: {claim['summary']}." if claim and claim.get("summary") else ""))
        if github.username else "No GitHub profile found in resume.",
        github=github if github.username else None, strengths=strengths[:5], concerns=concerns[:5],
        claim_verification=claim,
        evidence=evidence, scoring_method="rules+llm" if llm else "rules", notes=notes,
        eligibility_check=check,
    )


def _eligibility_check(elig, opinion, error) -> dict | None:
    """Audit record for borderline cases. The rule-based decision is always the final one;
    a disagreeing LLM opinion only sets needs_human_review."""
    if not elig.borderline_reasons:
        return None
    rules_decision = "eligible" if elig.eligible else "rejected"
    check: dict = {
        "borderline_reasons": elig.borderline_reasons,
        "rules_decision": rules_decision,
        "final_decision": rules_decision,
        "llm_second_opinion": None,
        "llm_agrees": None,
        "needs_human_review": False,
    }
    if opinion is not None:
        llm_says_eligible = opinion.python_is_genuine and opinion.builds_with_llm_or_agents
        check["llm_second_opinion"] = opinion.model_dump()
        check["llm_agrees"] = llm_says_eligible == elig.eligible
        check["needs_human_review"] = not check["llm_agrees"]
    elif error and error != "llm_disabled":
        check["second_opinion_error"] = error
    return check


def _name_is_weak(profile: CandidateProfile) -> bool:
    return not profile.name_confident


def _hint(profile, elig, rs: RuleScores | None) -> str:
    lines = [f"Rule-based eligibility: python={bool(elig.python_evidence)}, ai_level={elig.ai_evidence_level}"]
    if rs:
        lines.append(
            f"Rule scores: ai={rs.ai_before_penalty}/40 (penalty {rs.penalty}), python_backend={rs.python_backend}/30, "
            f"cloud={rs.cloud_fullstack}/15, eng={rs.engineering_depth}/5"
        )
    return "\n".join(lines)


def _rule_strengths(rs: RuleScores, elig) -> list[str]:
    out = []
    if rs.ai_projects:
        out.append(f"Substantive AI project(s): {', '.join(rs.ai_projects[:2])}")
    if rs.python_backend >= 18:
        out.append("Solid Python/backend evidence in projects")
    if rs.cloud_fullstack >= 8:
        out.append("Cloud/deployment experience")
    if rs.engineering_depth >= 3:
        out.append("Shows engineering depth (testing/caching/queues/etc.)")
    return out or ["Meets Python + AI eligibility"]


def _rule_concerns(rs: RuleScores, elig, profile) -> list[str]:
    out = list(rs.penalty_reasons)
    if rs.python_backend < 10:
        out.append("Limited Python/backend depth")
    if rs.cloud_fullstack < 4:
        out.append("Little cloud/deployment evidence")
    if not any(s in ("Redis", "PostgreSQL") for s in profile.skills):
        out.append("No Redis/PostgreSQL evidence")
    return out


def _rank(results: list[CandidateResult]) -> list[CandidateResult]:
    eligible = sorted(
        (r for r in results if r.eligible),
        key=lambda r: (-(r.total_score or 0), -(r.score_breakdown.ai_project_depth if r.score_breakdown else 0), r.candidate_name),
    )
    for i, r in enumerate(eligible, 1):
        r.rank = i
    return eligible


async def run_pipeline_async(input_dir: Path, settings: Settings | None = None, analyzer: ResumeAnalyzer | None | str = "auto") -> dict:
    settings = settings or Settings()
    t0 = time.perf_counter()
    report: IngestionReport = ingest_folder(input_dir)
    if analyzer == "auto":
        analyzer = build_analyzer(settings)
    llm_sem = asyncio.Semaphore(settings.llm_concurrency)
    gh = GitHubEnricher(settings.github_token, settings.github_concurrency, settings.github_timeout_s)
    results: list[CandidateResult] = []
    failed = list(report.failed)

    async def guarded(raw):
        try:
            return await _process_one(raw, settings, analyzer, llm_sem, gh)
        except Exception as exc:  # one bad resume must never sink the batch
            log.exception("Processing failed for %s", raw.filename)
            failed.append({"filename": raw.filename, "error": f"{type(exc).__name__}: {exc}"})
            return None

    try:
        done = await asyncio.gather(*(guarded(r) for r in report.resumes))
    finally:
        await gh.aclose()
        if hasattr(analyzer, "flush"):
            analyzer.flush()  # persist newly cached LLM answers
    results = [r for r in done if r]
    ranked = _rank(results)
    rejected = sorted((r for r in results if not r.eligible), key=lambda r: r.filename)
    gh_status: dict[str, int] = {}
    for r in results:
        if r.github:
            gh_status[r.github.status] = gh_status.get(r.github.status, 0) + 1
    llm_used = sum(1 for r in ranked if r.scoring_method == "rules+llm")
    return {
        "batch_summary": {
            "total_resumes": report.total_files,
            "successfully_parsed": len(report.resumes),
            "eligible": len(ranked),
            "rejected": len(rejected),
            "failed_or_unreadable": len(failed),
            "duplicates_skipped": len(report.duplicates),
            "scoring_method": f"rules+llm ({settings.openai_model})" if analyzer else "rules only",
            "llm_scored_candidates": llm_used,
            "llm_cache": getattr(analyzer, "stats", None) if analyzer else None,
            "github_enrichment": gh_status,
            "borderline_cases": sum(1 for r in results if r.eligibility_check),
            "second_opinions_obtained": sum(1 for r in results if r.eligibility_check and r.eligibility_check["llm_second_opinion"]),
            "needs_human_review": sum(1 for r in results if r.eligibility_check and r.eligibility_check["needs_human_review"]),
            "runtime_seconds": round(time.perf_counter() - t0, 1),
        },
        "ranked_candidates": [r.model_dump(exclude_none=True) for r in ranked],
        # "candidate" mirrors the key used in the assignment's suggested eligibility output
        "rejected_candidates": [{"candidate": r.candidate_name, **r.model_dump(exclude_none=True)} for r in rejected],
        "needs_human_review": [
            {
                "candidate_name": r.candidate_name, "filename": r.filename,
                "rules_decision": r.eligibility_check["rules_decision"],
                "borderline_reasons": r.eligibility_check["borderline_reasons"],
                "llm_reasoning": r.eligibility_check["llm_second_opinion"]["reasoning"],
            }
            for r in results if r.eligibility_check and r.eligibility_check["needs_human_review"]
        ],
        "failed_resumes": failed,
        "duplicates": report.duplicates,
    }


SPEC_KEYS = (
    "rank", "candidate_name", "eligible", "total_score", "score_breakdown", "matched_skills",
    "project_summary", "github_summary", "strengths", "concerns",
)


def to_spec_list(results: dict) -> list[dict]:
    """Ranked candidates only, as a bare list with exactly the keys of the example in section 7 of the assignment."""
    return [{k: r[k] for k in SPEC_KEYS} for r in results["ranked_candidates"]]


def run_pipeline(input_dir: Path, settings: Settings | None = None, analyzer="auto") -> dict:
    return asyncio.run(run_pipeline_async(input_dir, settings, analyzer))
