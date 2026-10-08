"""Claim-vs-proof: cross-check the technologies a resume claims against the candidate's public GitHub repos.

* Claims   = verifiable technologies named inside project / experience entries (not skills lists).
* Proof    = the technology also appears in the README, description, topics or dependency files of a repo
             (resume-linked repos first, then repos whose name matches a project title, then recent relevant repos).
* Result   = per-candidate report plus a small bonus (never a penalty: private/employer code is normal).
Everything here is advisory and failure-tolerant; any problem yields status "skipped"/"error", never a failed batch.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from . import config as cfg
from . import keywords as kw
from .models import Block

log = logging.getLogger(__name__)
REPO_URL_RE = re.compile(r"github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+)", re.IGNORECASE)


@dataclass
class RepoRef:
    owner: str
    name: str
    source: str  # linked_in_resume | name_match | recent_relevant


def claimed_techs(blocks: list[Block]) -> list[str]:
    """Verifiable technologies mentioned inside project/experience entries."""
    text = "\n".join(b.text for b in blocks)
    return [t for t in cfg.VERIFIABLE_TECHS if t in kw.SKILL_VOCAB and kw.SKILL_VOCAB[t].search(text)]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def select_repos(username: str, links: list[str], blocks: list[Block], repos: list[dict]) -> list[RepoRef]:
    """Pick at most MAX_CLAIM_REPOS repos, strongest link to the resume first."""
    chosen: list[RepoRef] = []
    seen: set[tuple[str, str]] = set()

    def add(owner: str, name: str, source: str) -> None:
        key = (owner.lower(), name.lower().removesuffix(".git"))
        if key not in seen and len(chosen) < cfg.MAX_CLAIM_REPOS:
            seen.add(key)
            chosen.append(RepoRef(owner, name.removesuffix(".git"), source))

    for link in links:  # 1. repos the resume links to directly
        m = REPO_URL_RE.search(link)
        if m and m.group(2).lower() not in ("", "issues", "pulls"):
            add(m.group(1), m.group(2), "linked_in_resume")
    titles = [_norm(b.text.splitlines()[0]) for b in blocks if b.is_ai]
    for r in repos:  # 2. repo name appears in an AI project's title (or vice versa)
        n = _norm(r["name"])
        if len(n) >= 5 and any(n in t or (len(t) >= 5 and t[:20] in n) for t in titles):
            add(username, r["name"], "name_match")
    for r in sorted((x for x in repos if not x.get("fork")), key=lambda x: x.get("pushed_at") or "", reverse=True):
        if r.get("relevant"):  # 3. most recent Python/AI-relevant repos
            add(username, r["name"], "recent_relevant")
    return chosen


CHECK_SCOPE = (
    "Claims were searched for in each repo's description/topics, README, dependency files (repo root and up to two folders "
    "down, e.g. backend/requirements.txt) and file/folder names. Source code, commit history and private repos were NOT "
    "scanned, so 'not confirmed' is not evidence that a claim is false."
)


def _first_source(pattern, sources: dict[str, str]) -> str | None:
    for label, text in sources.items():
        if pattern.search(text):
            return label
    return None


def judge(claims: list[str], evidences: list[tuple[RepoRef, dict]]) -> dict:
    """Pure function: combine repo evidence into the verification report (easy to unit-test)."""
    repos_out, verified = [], {}
    for ref, ev in evidences:
        sources = ev.get("sources") or ({"text": ev["text"]} if ev.get("text") else {})
        found: dict[str, str] = {}
        if not ev.get("fork"):  # a fork proves nothing about the candidate's own work
            for t in claims:
                label = _first_source(kw.SKILL_VOCAB[t], sources)
                if label:
                    found[t] = label
                    verified.setdefault(t, f"{ref.owner}/{ref.name}: {label}")
        repos_out.append({
            "repo": f"{ref.owner}/{ref.name}", "source": ref.source, "is_fork": ev.get("fork", False),
            "active_span_days": ev.get("active_span_days"), "has_readme": ev.get("has_readme", False),
            "files_listed": ev.get("files_listed"), "dependency_files_read": ev.get("manifests_read", []),
            "claimed_techs_found": sorted(found), "found_in": found,
        })
    ratio = len(verified) / len(claims) if claims else 0.0
    credible = any(not r["is_fork"] and (r["active_span_days"] or 0) >= 1 for r in repos_out)
    bonus = 0
    if len(claims) >= cfg.CLAIM_MIN_CLAIMS and credible:
        bonus = int(round(cfg.CLAIM_BONUS_MAX * ratio))
    unverified = [t for t in claims if t not in verified]
    notes = []
    if repos_out and not any(r["has_readme"] for r in repos_out):
        notes.append("none of the checked repos has a README, so little text was available")
    if any(r["is_fork"] for r in repos_out):
        notes.append("forked repos were ignored")
    summary = (
        f"{len(verified)} of {len(claims)} claimed technologies confirmed in {len(repos_out)} public repo(s) "
        "(README, description, dependency files, file names)"
        + (f"; not confirmed: {', '.join(unverified[:5])}. This does not mean the claim is false: source code was not scanned"
           if unverified else "")
        + (f" ({'; '.join(notes)})" if notes and unverified else "")
    )
    return {
        "status": "checked", "claims_total": len(claims), "claims_verified": len(verified),
        "verified_techs": sorted(verified), "verified_in": verified, "unverified_techs": unverified,
        "verified_ratio": round(ratio, 2), "repos_checked": repos_out, "score_bonus": bonus,
        "check_scope": CHECK_SCOPE, "summary": summary,
    }


async def verify_claims(username: str | None, links: list[str], blocks: list[Block], gh) -> dict | None:
    """Run the check. Returns None when there is nothing to check; never raises."""
    claims = claimed_techs([b for b in blocks if b.is_ai] or blocks)
    if not username or not claims:
        return None
    try:
        repos = await gh.list_repos(username)
        refs = select_repos(username, links, blocks, repos)
        if not refs:
            return {"status": "no_repos_found", "claims_total": len(claims), "score_bonus": 0,
                    "summary": "No public repo could be tied to the resume's projects."}
        evidences = []
        for ref in refs:
            ev = await gh.repo_evidence(ref.owner, ref.name)
            if ev:
                evidences.append((ref, ev))
        if not evidences:
            return {"status": "skipped", "claims_total": len(claims), "score_bonus": 0,
                    "summary": "Repo contents unavailable (rate limit, private or missing repos)."}
        return judge(claims, evidences)
    except Exception as exc:  # advisory feature: never break the candidate
        log.warning("claim check failed for %s: %s", username, exc)
        return {"status": "error", "claims_total": len(claims), "score_bonus": 0,
                "summary": f"Claim check failed: {type(exc).__name__}"}
