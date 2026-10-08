"""Hard, rule-based eligibility filter. Deliberately independent of any LLM."""
from __future__ import annotations

from . import keywords as kw
from .config import Settings
from .extraction import analyze_text_blocks, find_terms
from .models import Block, CandidateProfile, EligibilityResult, ResumeSections


WEAK_AI_MAX_TERMS = 2  # <= this many distinct LLM/retrieval/agent terms in project entries => weak AI evidence


def work_text(sections: ResumeSections) -> str:
    """Text describing things the candidate *did* (projects, experience, internships)."""
    if not sections.sectioned:
        return sections.evidence
    parts = [sections.sections.get(k, "") for k in ("projects", "experience", "other")]
    text = "\n".join(p for p in parts if p).strip()
    return text if len(text) >= 120 else sections.evidence


def work_blocks(profile: CandidateProfile) -> list[Block]:
    return analyze_text_blocks(work_text(profile.sections))


def _snippet(text: str, term: str, width: int = 70) -> str:
    i = text.lower().find(term.lower())
    if i < 0:
        return term
    s = text[max(0, i - width // 2): i + len(term) + width // 2]
    return " ".join(s.split())


def check_python(profile: CandidateProfile) -> tuple[list[str], str]:
    """Evidence that Python is a real skill / implementation language.
    Returns (evidence, level) with level in {"project", "skills_only", "none"}."""
    sec = profile.sections
    scan = "\n".join(v for k, v in sec.sections.items() if k not in ("education", "certifications")) \
        if sec.sectioned else profile.raw_text
    evidence: list[str] = []
    level = "project"
    work = work_text(sec)
    if kw.PYTHON_EXPLICIT.search(work):
        evidence.append("Python used in projects/experience: \"..." + _snippet(work, "python") + "...\"")
    elif kw.PYTHON_IMPLIED.search(work):
        t = find_terms(kw.PYTHON_IMPLIED, work)[0]
        evidence.append(f"Python-only framework in projects/experience: {t}")
    if not evidence and kw.PYTHON_EXPLICIT.search(scan):
        evidence.append("Python listed as a skill (no project-level evidence)")
        level = "skills_only"
    elif not evidence and kw.PYTHON_IMPLIED.search(scan):
        evidence.append(f"Python-only framework listed: {find_terms(kw.PYTHON_IMPLIED, scan)[0]}")
        level = "skills_only"
    return evidence, (level if evidence else "none")


def check_ai(profile: CandidateProfile, blocks: list[Block], settings: Settings) -> tuple[list[str], str]:
    """Return (evidence, level). level: llm_agentic | classical_ml | none."""
    evidence: list[str] = []
    for b in blocks:
        if b.is_ai:
            terms = sorted({t for ts in b.capabilities.values() for t in ts})[:6]
            title = b.text.splitlines()[0].lstrip("•●▪◦○■◆-–—*· 	")[:80]
            evidence.append(f"{title} -> {', '.join(terms)}")
    if evidence:
        return evidence[:5], "llm_agentic"
    if settings.allow_classical_ml:
        for b in blocks:
            if b.is_ml_only:
                terms = find_terms(kw.CLASSICAL_ML, b.text)[:5]
                evidence.append(f"{b.text.splitlines()[0].lstrip('•●▪◦○■◆-–—*· ')[:80]} -> {', '.join(terms)} (classical ML/CV, no LLM/agentic)")
        if evidence:
            return evidence[:3], "classical_ml"
    return [], "none"


def _anchor_terms(blocks: list[Block]) -> set[str]:
    """Distinct LLM / retrieval / agent terms found inside project and experience entries."""
    terms: set[str] = set()
    for b in blocks:
        if b.is_ai:
            for cap in kw.AI_ANCHORS:
                terms |= set(b.capabilities.get(cap, []))
    return terms


def find_borderline(profile: CandidateProfile, blocks: list[Block], eligible: bool, py_level: str, ai_level: str) -> list[str]:
    """Why the rule-based decision is thin enough to deserve a second opinion (empty = clear-cut)."""
    reasons: list[str] = []
    if eligible:
        if py_level == "skills_only":
            reasons.append("python_only_in_skills_list")
        if ai_level == "llm_agentic" and len(_anchor_terms(blocks)) <= WEAK_AI_MAX_TERMS:
            reasons.append("ai_evidence_is_thin")
        return reasons
    # rejected: only a near-miss if Python is fine and AI wording exists, but outside projects/experience
    if py_level != "none" and ai_level == "none" and profile.sections.sectioned:
        outside = " ".join([profile.sections.skills, profile.sections.sections.get("summary", "")])
        if any(kw.AI_CAPABILITIES[c].search(outside) for c in kw.AI_ANCHORS):
            reasons.append("ai_keywords_only_in_skills_or_summary")
    return reasons


def check_eligibility(profile: CandidateProfile, blocks: list[Block], settings: Settings) -> EligibilityResult:
    py, py_level = check_python(profile)
    ai, level = check_ai(profile, blocks, settings)
    reasons: list[str] = []
    if not py:
        reasons.append("No evidence of Python stack")
    if level == "none":
        listed = [t for t in profile.skills if t in {"LangChain", "LangGraph", "RAG", "LLMs", "OpenAI", "Agents", "Embeddings"}]
        if listed:
            reasons.append(f"No AI/agentic project evidence (AI keywords only in skills/summary: {', '.join(listed)})")
        else:
            reasons.append("No AI/agentic project evidence")
    eligible = not reasons
    return EligibilityResult(
        candidate=profile.name,
        eligible=eligible,
        borderline_reasons=find_borderline(profile, blocks, eligible, py_level, level),
        rejection_reasons=reasons,
        matched_skills=profile.skills,
        python_evidence=py,
        ai_evidence=ai,
        ai_evidence_level=level,
    )
