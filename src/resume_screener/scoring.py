"""Deterministic, explainable rubric. Every point is traceable to matched terms."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import config as cfg
from . import keywords as kw
from .eligibility import work_text
from .extraction import analyze_block, find_terms
from .models import Block, CandidateProfile, ResumeSections


@dataclass
class RuleScores:
    ai_project_depth: int = 0
    python_backend: int = 0
    cloud_fullstack: int = 0
    engineering_depth: int = 0
    ai_before_penalty: int = 0
    penalty: int = 0
    penalty_reasons: list[str] = field(default_factory=list)
    evidence: dict[str, list[str]] = field(default_factory=dict)
    ai_projects: list[str] = field(default_factory=list)
    thin_projects: list[str] = field(default_factory=list)


def _weighted_presence(patterns: dict, work: str, summary: str, skills: str, header_rest: str):
    """For each category: 1.0 if seen in work text, 0.5 in summary, SKILLS_ONLY_FACTOR if only listed."""
    found: dict[str, tuple[float, list[str]]] = {}
    for name, p in patterns.items():
        for text, w in ((work, 1.0), (summary, 0.5), (skills + "\n" + header_rest, cfg.SKILLS_ONLY_FACTOR)):
            terms = find_terms(p, text)
            if terms:
                found[name] = (w, terms)
                break
    return found


def _split_texts(sections: ResumeSections, full: str) -> tuple[str, str, str, str]:
    work = work_text(sections)
    if not sections.sectioned:
        return full, "", "", ""
    summary = sections.sections.get("summary", "")
    skills = sections.skills
    rest = sections.sections.get("header", "")
    return work, summary, skills, rest


def title_of(block: Block) -> str:
    first = block.text.splitlines()[0].lstrip("•●▪◦○■◆-–—*· 	")
    return first[:90]


def score_ai_depth(profile: CandidateProfile, blocks: list[Block], ai_level: str, rs: RuleScores) -> None:
    work, summary, skills, rest = _split_texts(profile.sections, profile.raw_text)
    ai_blocks = [b for b in blocks if b.is_ai]
    cap_points = cfg.AI_CAPABILITY_POINTS
    evidence = rs.evidence.setdefault("ai_project_depth", [])

    if ai_level == "classical_ml" or not ai_blocks:
        ml_blocks = [b for b in blocks if b.is_ml_only]
        pts = min(cfg.CLASSICAL_ML_AI_CAP, 4 + 2 * len(ml_blocks))
        rs.ai_before_penalty = pts
        rs.ai_project_depth = pts
        evidence.append(f"Classical ML/CV projects only ({len(ml_blocks)}); capped at {cfg.CLASSICAL_ML_AI_CAP}")
        return

    # capability weights: strongest evidence wins (work block > summary > skills list)
    caps_found: dict[str, tuple[float, list[str]]] = {}
    for b in ai_blocks:
        for cap, terms in b.capabilities.items():
            caps_found[cap] = (1.0, sorted(set(caps_found.get(cap, (0, []))[1]) | set(terms)))
    # claims in summary/skills only count partially, and only for capabilities not shown in projects
    anchor_ok = True
    for text, w in ((summary, 0.5), (skills + "\n" + rest, cfg.SKILLS_ONLY_FACTOR)):
        for cap, p in kw.AI_CAPABILITIES.items():
            terms = find_terms(p, text)
            if terms and cap not in caps_found and anchor_ok:
                caps_found[cap] = (w, terms)

    total = 0.0
    for cap, pts in cap_points.items():
        if cap in caps_found:
            w, terms = caps_found[cap]
            total += pts * w
            tag = "projects" if w == 1.0 else "summary" if w == 0.5 else "skills list only"
            evidence.append(f"{cap} ({tag}): {', '.join(terms[:5])}")

    # depth: independent substantive AI projects = >=2 distinct capabilities beyond bare LLM usage
    substantive = []
    for b in ai_blocks:
        deep_caps = set(b.capabilities) - {"llm_usage", "prompting"}
        if len(deep_caps) >= 2 and not b.thin:
            substantive.append(b)
    rs.ai_projects = [title_of(b) for b in substantive]
    if len(substantive) >= 2:
        total += cfg.AI_MULTI_PROJECT_BONUS
        evidence.append(f"{len(substantive)} substantive AI projects: " + "; ".join(title_of(b) for b in substantive[:3]))
    elif len(substantive) == 1:
        total += 1
        evidence.append(f"1 substantive AI project: {title_of(substantive[0])}")

    base = int(round(min(total, cfg.WEIGHTS["ai_project_depth"])))
    rs.ai_before_penalty = base

    # ---- project-quality penalties
    penalty = 0
    thin = [b for b in ai_blocks if b.thin]
    rs.thin_projects = [title_of(b) for b in thin]
    if thin and len(thin) == len(ai_blocks):
        penalty += cfg.PENALTY_ALL_THIN
        rs.penalty_reasons.append(f"All AI projects look like thin LLM-API wrappers (-{cfg.PENALTY_ALL_THIN}): " + "; ".join(rs.thin_projects[:2]))
    elif thin:
        penalty += cfg.PENALTY_SOME_THIN
        rs.penalty_reasons.append(f"Some AI projects are thin LLM-API wrappers (-{cfg.PENALTY_SOME_THIN}): " + "; ".join(rs.thin_projects[:2]))
    unowned = [b for b in ai_blocks if not b.owned]
    if unowned and len(unowned) == len(ai_blocks):
        penalty += cfg.PENALTY_TUTORIAL
        rs.penalty_reasons.append(f"AI projects described without implementation/ownership detail (-{cfg.PENALTY_TUTORIAL})")
    penalty = min(penalty, cfg.PENALTY_MAX)
    rs.penalty = penalty
    rs.ai_project_depth = max(0, base - penalty)


def score_python_backend(profile: CandidateProfile, rs: RuleScores) -> None:
    work, summary, skills, rest = _split_texts(profile.sections, profile.raw_text)
    found = _weighted_presence(kw.BACKEND_TERMS, work, summary, skills, rest)
    total = 0.0
    ev = rs.evidence.setdefault("python_backend", [])
    for name, pts in cfg.BACKEND_POINTS.items():
        if name in found:
            w, terms = found[name]
            total += pts * w
            tag = "in projects/experience" if w == 1.0 else "summary" if w == 0.5 else "skills list only"
            ev.append(f"{name} ({tag}): {', '.join(terms[:4])}")
    rs.python_backend = int(round(min(total, cfg.WEIGHTS["python_backend"])))


def score_cloud(profile: CandidateProfile, rs: RuleScores) -> None:
    work, summary, skills, rest = _split_texts(profile.sections, profile.raw_text)
    found = _weighted_presence(kw.CLOUD_TERMS, work, summary, skills, rest)
    backend_found = _weighted_presence(kw.BACKEND_TERMS, work, summary, skills, rest)
    total = 0.0
    ev = rs.evidence.setdefault("cloud_fullstack", [])
    for name, pts in cfg.CLOUD_POINTS.items():
        if name not in found:
            continue
        w, terms = found[name]
        if name == "other_cloud" and "gcp" in found:
            continue  # GCP already rewarded; don't double count clouds
        if name == "frontend" and not ({"web_framework", "api_design", "orm_tasks"} & set(backend_found)):
            continue  # React/Next.js only count as part of an end-to-end system
        total += pts * w
        tag = "in projects/experience" if w == 1.0 else "summary" if w == 0.5 else "skills list only"
        ev.append(f"{name} ({tag}): {', '.join(terms[:4])}")
    rs.cloud_fullstack = int(round(min(total, cfg.WEIGHTS["cloud_fullstack"])))


def score_engineering(profile: CandidateProfile, rs: RuleScores) -> None:
    work, summary, skills, rest = _split_texts(profile.sections, profile.raw_text)
    ev = rs.evidence.setdefault("engineering_depth", [])
    hits = 0.0
    for name, p in kw.ENGINEERING_TERMS.items():
        terms = find_terms(p, work)
        if terms:
            hits += 1.0
            ev.append(f"{name}: {', '.join(terms[:3])}")
        elif find_terms(p, summary + "\n" + skills):
            hits += 0.3
    rs.engineering_depth = int(round(min(hits * 5 / 4, cfg.WEIGHTS["engineering_depth"])))  # 4 distinct signals = full marks


def rule_score(profile: CandidateProfile, blocks: list[Block], ai_level: str) -> RuleScores:
    rs = RuleScores()
    score_ai_depth(profile, blocks, ai_level, rs)
    score_python_backend(profile, rs)
    score_cloud(profile, rs)
    score_engineering(profile, rs)
    return rs


def github_free_total(rs: RuleScores) -> int:
    return rs.ai_project_depth + rs.python_backend + rs.cloud_fullstack + rs.engineering_depth
