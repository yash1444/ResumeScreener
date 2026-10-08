"""Keyword vocabularies, loaded from keywords.yaml (edit that file, not this one).

Set KEYWORDS_FILE=/path/to/file.yaml to use a different vocabulary. The file is validated on load: a missing
section or an invalid regex raises KeywordConfigError naming the offending entry.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).with_name("keywords.yaml")

LIST_SECTIONS = (
    "python_explicit", "python_implied", "weak_agent", "classical_ml", "ownership_verbs", "thin_escape",
)
MAP_SECTIONS = (
    "ai_capabilities", "backend_terms", "cloud_terms", "engineering_terms", "skill_vocab", "section_headings",
)


class KeywordConfigError(ValueError):
    pass


def rx(*patterns: str) -> re.Pattern[str]:
    """Case-insensitive alternation of the given regex fragments."""
    return re.compile("|".join(patterns), re.IGNORECASE)


def _compile(patterns, where: str) -> re.Pattern[str]:
    if not isinstance(patterns, list) or not patterns or not all(isinstance(p, str) and p for p in patterns):
        raise KeywordConfigError(f"'{where}' must be a non-empty list of regex strings")
    for p in patterns:
        try:
            re.compile(p)
        except re.error as exc:
            raise KeywordConfigError(f"invalid regex in '{where}': {p!r} ({exc})") from exc
    return rx(*patterns)


def load_keywords(path: str | os.PathLike | None = None) -> dict:
    path = Path(path or os.getenv("KEYWORDS_FILE") or DEFAULT_PATH)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise KeywordConfigError(f"cannot read keyword file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise KeywordConfigError(f"{path} must contain a YAML mapping")
    out: dict = {}
    for name in LIST_SECTIONS:
        if name not in data:
            raise KeywordConfigError(f"{path}: missing section '{name}'")
        out[name] = _compile(data[name], name)
    for name in MAP_SECTIONS:
        section = data.get(name)
        if not isinstance(section, dict) or not section:
            raise KeywordConfigError(f"{path}: section '{name}' must be a non-empty mapping")
        out[name] = {key: _compile(val, f"{name}.{key}") for key, val in section.items()}
    anchors = data.get("ai_anchors")
    if not isinstance(anchors, list) or not anchors or any(a not in out["ai_capabilities"] for a in anchors):
        raise KeywordConfigError(f"{path}: 'ai_anchors' must list names defined in 'ai_capabilities'")
    out["ai_anchors"] = tuple(anchors)
    for needed in ("llm_usage", "retrieval", "agents"):
        if needed not in out["ai_capabilities"]:
            raise KeywordConfigError(f"{path}: 'ai_capabilities' must define '{needed}'")
    return out


_KW = load_keywords()

# Public names used by the rest of the package (unchanged API).
PYTHON_EXPLICIT = _KW["python_explicit"]
PYTHON_IMPLIED = _KW["python_implied"]
AI_CAPABILITIES = _KW["ai_capabilities"]
AI_ANCHORS = _KW["ai_anchors"]
WEAK_AGENT = _KW["weak_agent"]
CLASSICAL_ML = _KW["classical_ml"]
OWNERSHIP_VERBS = _KW["ownership_verbs"]
THIN_ESCAPE = _KW["thin_escape"]
BACKEND_TERMS = _KW["backend_terms"]
CLOUD_TERMS = _KW["cloud_terms"]
ENGINEERING_TERMS = _KW["engineering_terms"]
SKILL_VOCAB = _KW["skill_vocab"]
SECTION_HEADINGS = _KW["section_headings"]
