"""Turn raw resume text into a structured CandidateProfile (deterministic, no network)."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from . import keywords as kw
from .models import Block, CandidateProfile, RawResume, ResumeSections

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
GITHUB_RE = re.compile(r"github\.com/\s*([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))(?![A-Za-z0-9-])", re.IGNORECASE)
GITHUB_RESERVED = {
    "features", "orgs", "topics", "about", "sponsors", "login", "settings", "marketplace", "enterprise",
    "pricing", "apps", "explore", "collections", "events", "notifications", "pulls", "issues", "search",
    "site", "security", "readme", "new", "join", "contact", "trending", "customer-stories", "premium-support",
}
BULLET_RE = re.compile(r"^\s*(?:[•●▪◦○■◆\-–—*·]|•)\s*")
NAME_STOP = re.compile(r"resume|curriculum|vitae|engineer|developer|student|intern\b|summary|profile|objective", re.I)


# ----------------------------------------------------------------- sections
def _heading_key(line: str) -> str | None:
    s = line.strip().strip(":").strip("•●-–— ").strip()
    if not s or len(s) > 50 or len(s.split()) > 6 or BULLET_RE.match(line):
        return None
    norm = re.sub(r"\s+", " ", s.lower())
    for key, pattern in kw.SECTION_HEADINGS.items():
        if pattern.search(norm):
            return key
    # loose forms such as "Technical Projects", "Internship Experience"
    if re.fullmatch(r"(?:[\w&]+ ){0,3}projects?", norm):
        return "projects"
    if re.fullmatch(r"(?:[\w&]+ ){0,2}experience", norm):
        return "experience"
    return None


def _plausible_heading(line: str, prev: str, blank_before: bool) -> bool:
    """Reject wrapped-text fragments that merely look like headings ('project', 'educational QA', 'academic information.')."""
    s = line.strip()
    if s.endswith(".") or any(q in s for q in ('"', "\u201c", "\u201d")):
        return False
    if s[:1].islower():  # a real heading may start lower-case only after a finished line
        return blank_before or not prev or prev.rstrip().endswith((".", ":", ")", "%", "!"))
    return True


def split_sections(text: str) -> ResumeSections:
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    found = False
    prev, blank_before = "", False
    for line in text.splitlines():
        key = _heading_key(line)
        if key and not _plausible_heading(line, prev, blank_before):
            key = None
        if line.strip():
            prev, blank_before = line, False
        else:
            blank_before = True
        if key:
            found = True
            current = key
            sections.setdefault(current, [])
            continue
        sections[current].append(line)
    joined = {k: "\n".join(v).strip() for k, v in sections.items() if v}
    if not found:
        return ResumeSections(sections={"header": text}, evidence=text, skills="", sectioned=False)
    skills = joined.get("skills", "")
    evidence = "\n".join(joined.get(k, "") for k in ("summary", "projects", "experience", "other")).strip()
    if len(evidence) < 200:  # headings were not usable -> fall back to everything but skills/education
        evidence = "\n".join(v for k, v in joined.items() if k not in ("skills", "education", "certifications"))
    return ResumeSections(sections=joined, evidence=evidence, skills=skills, sectioned=True)


def split_blocks(text: str) -> list[Block]:
    """Group lines into project/job entries: a title line followed by its bullets."""
    blocks: list[list[str]] = []
    cur: list[str] = []
    prev_closed = True  # previous line ended a sentence / was a title
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        is_bullet = bool(BULLET_RE.match(line))
        looks_title = (
            not is_bullet and prev_closed and len(line) < 130 and line[0].isupper()
            and (len(line.split()) <= 14 or "|" in line)
        )
        if looks_title and cur and any(BULLET_RE.match(c) or len(c) > 90 for c in cur):
            blocks.append(cur)
            cur = []
        cur.append(line)
        prev_closed = line.endswith((".", ")", "%", "!")) or looks_title or is_bullet and line.endswith(".")
    if cur:
        blocks.append(cur)
    return [Block(text="\n".join(b)) for b in blocks if len(" ".join(b)) > 40]


# ------------------------------------------------------------- block analysis
def find_terms(pattern: re.Pattern[str], text: str) -> list[str]:
    return sorted({m.group(0).lower() for m in pattern.finditer(text)})


def analyze_block(block: Block) -> Block:
    text = block.text
    caps = {name: find_terms(p, text) for name, p in kw.AI_CAPABILITIES.items()}
    caps = {k: v for k, v in caps.items() if v}
    # the bare words "agent(s)" / "orchestrat…" only count beside a real LLM/retrieval signal
    agents = caps.get("agents", [])
    strong_agents = [a for a in agents if not kw.WEAK_AGENT.fullmatch(a)]
    anchored = bool(caps.get("llm_usage") or caps.get("retrieval") or strong_agents)
    if agents and not strong_agents and not anchored:
        caps.pop("agents")
    block.is_ai = anchored
    if not anchored:
        caps = {}
    block.capabilities = caps
    block.is_ml_only = (not anchored) and bool(kw.CLASSICAL_ML.search(text))
    block.owned = bool(kw.OWNERSHIP_VERBS.search(text))
    if anchored and "llm_usage" in caps:
        without_llm = kw.AI_CAPABILITIES["llm_usage"].sub(" ", text)
        deep = caps.get("retrieval") or strong_agents or caps.get("state_workflow") or caps.get("evaluation")
        block.thin = not deep and not kw.THIN_ESCAPE.search(without_llm)
    return block


def analyze_text_blocks(text: str) -> list[Block]:
    return [analyze_block(b) for b in split_blocks(text)]


# ----------------------------------------------------------------- identity
def extract_email(text: str, links: list[str]) -> str | None:
    for link in links:
        if link.lower().startswith("mailto:"):
            m = EMAIL_RE.search(link)
            if m:
                return m.group(0).lower()
    m = EMAIL_RE.search(text)
    return m.group(0).lower() if m else None


NAME_BAD_WORDS = re.compile(r"university|college|institute|school|simulation|engineering|technolog|summary|skills|experience|education|projects?|contact|address|bachelor|master|science|software|full|stack|data|analyst|intern", re.I)


def extract_name(text: str, filename: str) -> tuple[str, bool]:
    """Return (name, confident). Looks for a short, capitalised, letters-only line near the top."""
    for line in text.splitlines()[:8]:
        s = re.sub(r"\s+", " ", line).strip().rstrip(",")
        if not s or any(ch.isdigit() for ch in s) or "@" in s or "|" in s or "http" in s.lower():
            continue
        words = s.split()
        if not (1 <= len(words) <= 4) or NAME_STOP.search(s) or NAME_BAD_WORDS.search(s):
            continue
        if all(re.fullmatch(r"[A-Z][A-Za-z.'-]*", w) for w in words) and (len(words) >= 2 or len(s) >= 4):
            return (s.title() if s.isupper() else s), True
    return Path(filename).stem.replace("_", " ").title(), False


def extract_github(text: str, links: list[str]) -> tuple[str | None, str | None]:
    usernames: Counter[str] = Counter()
    for source in (*links, text):
        for m in GITHUB_RE.finditer(source):
            user = m.group(1)
            if user.lower() not in GITHUB_RESERVED:
                usernames[user] += 1
    if not usernames:
        return None, None
    user = usernames.most_common(1)[0][0]
    return user, f"https://github.com/{user}"


def extract_skills(text: str) -> list[str]:
    return [name for name, p in kw.SKILL_VOCAB.items() if p.search(text)]


def section_quality(sec: ResumeSections) -> float:
    """How plausible is this split? Rewards substantial skills/projects/experience text, penalises a huge unsectioned header."""
    if not sec.sectioned:
        return 0.0
    score = sum(1.0 for k in ("skills", "projects", "experience") if len(sec.sections.get(k, "")) >= 40)
    score += 0.5 if len(sec.sections.get("summary", "")) >= 40 else 0.0
    if len(sec.sections.get("header", "")) > 1000:
        score -= 1.0
    return score


def choose_reading_order(raw: RawResume) -> tuple[str, ResumeSections, bool]:
    """Use the PDF's own text order unless the geometric order clearly yields better sections (scrambled block order)."""
    sections = split_sections(raw.text)
    if raw.alt_text and raw.alt_text != raw.text:
        alt = split_sections(raw.alt_text)
        if section_quality(alt) > section_quality(sections) + 0.5:
            return raw.alt_text, alt, True
    return raw.text, sections, False


def build_profile(raw: RawResume) -> CandidateProfile:
    text, sections, reordered = choose_reading_order(raw)
    user, url = extract_github(text, raw.links)
    name, confident = extract_name(text, raw.filename)
    return CandidateProfile(
        filename=raw.filename,
        name=name,
        name_confident=confident,
        email=extract_email(raw.text, raw.links),
        github_username=user,
        github_url=url,
        skills=extract_skills(text),
        sections=sections,
        raw_text=text,
        reordered=reordered,
    )
