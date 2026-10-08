"""LLM answer cache: hits, misses, invalidation, persistence, failure handling."""
import asyncio
import json
from pathlib import Path

import pytest

from resume_screener.llm import CachingAnalyzer
from resume_screener.models import CategoryJudgement, EligibilityOpinion, LLMAnalysis


def _analysis(name="Jane"):
    j = CategoryJudgement(score=10, evidence=["e"])
    return LLMAnalysis(candidate_name=name, ai_project_depth=j, python_backend=j, cloud_fullstack=j, engineering_depth=j, project_summary="s")


def _opinion():
    return EligibilityOpinion(python_is_genuine=True, python_evidence="x", builds_with_llm_or_agents=True, ai_evidence="y", confidence="high", reasoning="r")


class Inner:
    def __init__(self, fail=False):
        self.calls, self.fail = 0, fail

    async def analyze(self, text, hint):
        self.calls += 1
        if self.fail:
            raise RuntimeError("model down")
        return _analysis(text[:4])

    async def second_opinion(self, text, reasons):
        self.calls += 1
        return _opinion()


def run(coro):
    return asyncio.run(coro)


def test_second_identical_call_is_served_from_cache(tmp_path):
    inner = Inner()
    c = CachingAnalyzer(inner, "m1", tmp_path / "c.json")
    a = run(c.analyze("resume text", "hint"))
    b = run(c.analyze("resume text", "hint"))
    assert inner.calls == 1 and a == b and c.stats == {"hits": 1, "misses": 1}


def test_any_change_in_input_model_or_kind_is_a_miss(tmp_path):
    inner = Inner()
    c = CachingAnalyzer(inner, "m1", tmp_path / "c.json")
    run(c.analyze("text A", "h"))
    run(c.analyze("text B", "h"))  # different resume
    run(c.analyze("text A", "other hint"))  # different rule hint
    assert inner.calls == 3
    run(c.second_opinion("text A", ["r1"]))
    run(c.second_opinion("text A", ["r1"]))
    run(c.second_opinion("text A", ["r2"]))
    assert inner.calls == 5  # one hit among the second-opinion calls
    other_model = CachingAnalyzer(inner, "m2", tmp_path / "c.json")
    other_model._data = dict(c._data)
    run(other_model.analyze("text A", "h"))
    assert inner.calls == 6  # same text, different model: not reused


def test_cache_persists_across_runs_and_survives_a_corrupt_file(tmp_path):
    path = tmp_path / "sub" / "c.json"
    first = CachingAnalyzer(Inner(), "m1", path)
    run(first.analyze("resume", "h"))
    first.flush()
    assert path.exists() and json.loads(path.read_text(encoding="utf-8"))
    inner = Inner()
    second = CachingAnalyzer(inner, "m1", path)  # a "new run"
    run(second.analyze("resume", "h"))
    assert inner.calls == 0 and second.stats["hits"] == 1
    path.write_text("{not json", encoding="utf-8")
    assert CachingAnalyzer(Inner(), "m1", path)._data == {}  # corrupt file: start empty, do not crash


def test_failures_are_not_cached(tmp_path):
    inner = Inner(fail=True)
    c = CachingAnalyzer(inner, "m1", tmp_path / "c.json")
    with pytest.raises(RuntimeError):
        run(c.analyze("resume", "h"))
    inner.fail = False
    run(c.analyze("resume", "h"))
    assert inner.calls == 2 and c.stats == {"hits": 0, "misses": 1}


def test_entry_that_no_longer_matches_the_schema_is_recomputed(tmp_path):
    inner = Inner()
    c = CachingAnalyzer(inner, "m1", tmp_path / "c.json")
    run(c.analyze("resume", "h"))
    key = next(iter(c._data))
    c._data[key] = {"unexpected": "shape"}
    run(c.analyze("resume", "h"))
    assert inner.calls == 2


def test_pipeline_reports_cache_stats_and_is_reproducible_from_cache(tmp_path):
    import samples as S
    from resume_screener.config import Settings
    from resume_screener.pipeline import run_pipeline

    class Rich(Inner):
        async def analyze(self, text, hint):
            self.calls += 1
            return _analysis("Asha Rao")

    src = tmp_path / "in"
    src.mkdir()
    (src / "a.txt").write_text(S.STRONG)
    inner = Inner()
    inner.analyze = Rich().analyze
    cache = CachingAnalyzer(inner, "m1", tmp_path / "c.json")
    out1 = run_pipeline(src, Settings(openai_api_key=None, github_token=None), analyzer=cache)
    out2 = run_pipeline(src, Settings(openai_api_key=None, github_token=None), analyzer=cache)
    assert out1["batch_summary"]["llm_cache"]["misses"] == 1 and out2["batch_summary"]["llm_cache"]["hits"] == 1
    assert out1["ranked_candidates"] == out2["ranked_candidates"]
    assert Path(tmp_path / "c.json").exists()  # flushed by the pipeline
