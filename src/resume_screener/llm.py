"""LLM adapter. Provider-specific code lives only in OpenAIAnalyzer; swap it by
implementing `ResumeAnalyzer.analyze`. Output is validated against LLMAnalysis."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Protocol

from .config import Settings
from .models import EligibilityOpinion, LLMAnalysis

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a strict, fair technical recruiter screening SDE-intern resumes for a role that needs
strong Python fundamentals and practical AI/agentic-systems experience.

Judge ONLY what the resume text shows. Prefer evidence of HOW something was built (projects, internships)
over keyword lists. Never award points for a framework that is only named in a skills list.

Score these categories (integers, within the maxima):
- ai_project_depth (0-40): real AI systems - agents, RAG, tool calling, retrieval, state, orchestration,
  evaluation, meaningful business logic. Give this score AFTER judging quality, but before any penalty.
- python_backend (0-30): Python, FastAPI/Django/Flask, async, PostgreSQL, Redis - evidenced in projects/internships.
- cloud_fullstack (0-15): GCP/AWS, Docker, deployment; React/Next.js count only as part of an end-to-end system.
- engineering_depth (0-5): testing, architecture, caching, queues, observability, concurrency, failure handling.

penalty (0-15): deduct 5-15 when the "AI project" is a thin wrapper around an LLM/API call with no workflow,
retrieval, state, evaluation or backend logic, or is tutorial-style with no sign of ownership. 0 if projects are solid.
List the offending project titles in thin_wrapper_projects / tutorial_style_projects.

Every category needs 1-3 short evidence items (<=25 words) taken from the resume. project_summary is one or two
sentences about the candidate's best AI project. strengths and concerns are short phrases (max 4 each).
Calibration: be discriminating. Typical intern profiles land at 30-60% of a category's maximum; full marks are rare and
need clear project-level evidence. Strengths and concerns must be specific to THIS resume (name the project or
technology); no generic filler such as "good communication" or "potential over-reliance".
Do not score GitHub (handled elsewhere). Do not decide eligibility."""


SECOND_OPINION_PROMPT = """You are double-checking an automated resume screen. A rule engine decided whether this
candidate meets BOTH minimum requirements for an SDE internship, but its evidence was thin, so give an independent opinion.

1. Python: Python is a real skill or implementation language of the candidate (used in a project or job, or clearly
   part of their stack) - not an incidental word.
2. AI/agentic work: the candidate BUILT or integrated something with an LLM, RAG / embeddings / vector search, or an
   agent (tool calling, multi-step workflows). This is FALSE if the candidate only USED AI tools to write their own code
   (Copilot, ChatGPT, Cursor, Claude Code), if AI appears only in a skills list or buzzword summary, or if the work is
   classical machine learning / computer vision only (CNNs, scikit-learn, OpenCV, YOLO).

Judge only what the resume text shows. Quote short evidence (<=25 words) or write 'none'. Be literal and conservative.
Do not rank or score the candidate."""


class ResumeAnalyzer(Protocol):
    async def analyze(self, resume_text: str, rule_hint: str) -> LLMAnalysis: ...

    async def second_opinion(self, resume_text: str, reasons: list[str]) -> EligibilityOpinion: ...


class OpenAIAnalyzer:
    def __init__(self, settings: Settings):
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.llm_timeout_s, max_retries=2)
        self._model = settings.openai_model
        self._max_chars = settings.max_resume_chars

    async def analyze(self, resume_text: str, rule_hint: str) -> LLMAnalysis:
        user = (
            f"Rule-based pre-analysis (for reference only, you may disagree):\n{rule_hint}\n\n"
            f"=== RESUME ===\n{resume_text[: self._max_chars]}"
        )
        completion = await self._client.chat.completions.parse(
            model=self._model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
            response_format=LLMAnalysis,
            temperature=0,
        )
        message = completion.choices[0].message
        if message.refusal or message.parsed is None:
            raise ValueError(f"model returned no structured output ({message.refusal or 'empty'})")
        return message.parsed


    async def second_opinion(self, resume_text: str, reasons: list[str]) -> EligibilityOpinion:
        user = (
            "Why the rule engine was unsure: " + ", ".join(reasons) + "\n\n=== RESUME ===\n" + resume_text[: self._max_chars]
        )
        completion = await self._client.chat.completions.parse(
            model=self._model,
            messages=[{"role": "system", "content": SECOND_OPINION_PROMPT}, {"role": "user", "content": user}],
            response_format=EligibilityOpinion,
            temperature=0,
        )
        message = completion.choices[0].message
        if message.refusal or message.parsed is None:
            raise ValueError(f"model returned no structured output ({message.refusal or 'empty'})")
        return message.parsed


LLM_CACHE_PATH = Path(".cache/llm.json")


class CachingAnalyzer:
    """Disk cache around any ResumeAnalyzer (provider-independent).

    The key is a hash of the call kind, model, prompt text, output schema and the exact input, so changing the model, a prompt
    or a schema invalidates old entries automatically. Only successful, schema-valid answers are stored; failures are never
    cached. Identical input therefore gives an identical, free answer on re-runs (reproducible and cheaper).
    The cache holds resume-derived text, so it lives in the git-ignored .cache/ folder; delete that folder to purge it.
    """

    def __init__(self, inner, model: str, path: Path | str = LLM_CACHE_PATH):
        self._inner, self._model, self._path = inner, model, Path(path)
        self._data: dict[str, dict] = self._load()
        self._dirty = False
        self.hits = 0
        self.misses = 0

    def _load(self) -> dict:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:  # missing or corrupt cache: start empty
            return {}

    def _key(self, kind: str, prompt: str, schema, text: str, extra: str) -> str:
        parts = [kind, self._model, prompt, json.dumps(schema.model_json_schema(), sort_keys=True), text, extra]
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()

    async def _cached(self, key: str, schema, call):
        stored = self._data.get(key)
        if stored is not None:
            try:
                result = schema.model_validate(stored)
                self.hits += 1
                return result
            except Exception:  # entry no longer matches the schema: recompute
                pass
        result = await call()  # errors propagate and are never cached
        self.misses += 1
        self._data[key] = result.model_dump()
        self._dirty = True
        return result

    async def analyze(self, resume_text: str, rule_hint: str) -> LLMAnalysis:
        key = self._key("analyze", SYSTEM_PROMPT, LLMAnalysis, resume_text, rule_hint)
        return await self._cached(key, LLMAnalysis, lambda: self._inner.analyze(resume_text, rule_hint))

    async def second_opinion(self, resume_text: str, reasons: list[str]) -> EligibilityOpinion:
        key = self._key("second_opinion", SECOND_OPINION_PROMPT, EligibilityOpinion, resume_text, "|".join(reasons))
        return await self._cached(key, EligibilityOpinion, lambda: self._inner.second_opinion(resume_text, reasons))

    def flush(self) -> None:
        """Write new entries to disk (atomic replace); best-effort, never raises."""
        if not self._dirty:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data), encoding="utf-8")
            os.replace(tmp, self._path)
            self._dirty = False
        except Exception as exc:
            log.warning("could not write the LLM cache: %s", exc)

    @property
    def stats(self) -> dict:
        return {"hits": self.hits, "misses": self.misses}


def build_analyzer(settings: Settings) -> ResumeAnalyzer | None:
    """None -> the pipeline runs rules-only (no key, or the SDK is missing)."""
    if not settings.openai_api_key:
        log.warning("OPENAI_API_KEY not set: running rule-based scoring only")
        return None
    try:
        analyzer = OpenAIAnalyzer(settings)
    except Exception as exc:  # pragma: no cover
        log.warning("LLM adapter unavailable (%s): running rule-based scoring only", exc)
        return None
    return CachingAnalyzer(analyzer, settings.openai_model) if settings.llm_cache_enabled else analyzer


async def safe_analyze(analyzer: ResumeAnalyzer | None, sem: asyncio.Semaphore, text: str, hint: str):
    """Returns (analysis | None, error | None). Never raises."""
    if analyzer is None:
        return None, "llm_disabled"
    try:
        async with sem:
            return await analyzer.analyze(text, hint), None
    except Exception as exc:
        log.warning("LLM analysis failed: %s", exc)
        return None, f"{type(exc).__name__}: {str(exc)[:160]}"


async def safe_second_opinion(analyzer, sem: asyncio.Semaphore, text: str, reasons: list[str]):
    """Returns (opinion | None, error | None). Never raises; analyzers without the method are skipped."""
    method = getattr(analyzer, "second_opinion", None)
    if method is None:
        return None, "llm_disabled"
    try:
        async with sem:
            return await method(text, reasons), None
    except Exception as exc:
        log.warning("LLM second opinion failed: %s", exc)
        return None, f"{type(exc).__name__}: {str(exc)[:160]}"
