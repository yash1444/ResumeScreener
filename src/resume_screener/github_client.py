"""Lightweight, cached, failure-tolerant GitHub enrichment (public REST API)."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

import httpx

from . import config as cfg
from . import keywords as kw
from .models import GitHubResult

log = logging.getLogger(__name__)
API = "https://api.github.com"
CACHE_FILE = Path(".cache/github.json")
CACHE_TTL_S = 6 * 3600  # re-runs within 6h reuse results and do not burn the unauthenticated quota
AI_REPO_HINT = kw.rx(r"\bai\b", r"\bllm", r"\brag\b", r"agent", r"langchain", r"langgraph", r"openai", r"gpt", r"embedding", r"vector", r"\bml\b", r"machine-learning", r"deep-learning", r"nlp", r"chatbot", r"generative", r"transformer")


class RateLimited(Exception):
    pass


class GitHubEnricher:
    """One instance per run: owns the HTTP client, a result cache and a concurrency limit."""

    def __init__(self, token: str | None, concurrency: int = 5, timeout: float = 15.0):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "resume-screener"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(headers=headers, timeout=timeout, base_url=API)
        self._sem = asyncio.Semaphore(concurrency)
        self._cache: dict[str, GitHubResult] = {}
        self._inflight: dict[str, asyncio.Task] = {}
        self._disk = self._load_disk()
        self._repos: dict[str, list[dict]] = {}
        self._evidence: dict[str, dict | None] = {}
        self._rate_limited = False
        self._remaining: int | None = None
        self.authenticated = bool(token)

    @staticmethod
    def _load_disk() -> dict:
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_disk(self) -> None:
        try:
            CACHE_FILE.parent.mkdir(exist_ok=True)
            CACHE_FILE.write_text(json.dumps(self._disk), encoding="utf-8")
        except Exception:  # cache is best-effort
            pass

    async def aclose(self) -> None:
        self._save_disk()
        await self._client.aclose()

    async def _get(self, path: str, **params):
        if self._rate_limited:
            raise RateLimited("GitHub rate limit already hit in this run")
        async with self._sem:
            resp = await self._client.get(path, params=params)
        self._remaining = int(resp.headers.get("x-ratelimit-remaining", self._remaining or 999))
        if resp.status_code == 429 or (resp.status_code == 403 and (self._remaining == 0 or "rate limit" in resp.text.lower())):
            self._rate_limited = True
            raise RateLimited("GitHub API rate limit exceeded")
        return resp

    async def enrich(self, username: str | None) -> GitHubResult:
        if not username:
            return GitHubResult()
        key = username.lower()
        if key in self._cache:
            return self._cache[key]
        hit = self._disk.get(key)
        if hit and time.time() - hit["ts"] < CACHE_TTL_S and hit["data"].get("status") in ("ok", "partial", "not_found"):
            self._cache[key] = GitHubResult(**hit["data"])
            return self._cache[key]
        if key not in self._inflight:  # de-duplicate concurrent lookups of the same user
            self._inflight[key] = asyncio.create_task(self._fetch(username))
        result = await self._inflight[key]
        self._cache[key] = result
        self._disk[key] = {"ts": time.time(), "data": result.model_dump()}
        return result

    # ---- repo-level data for the claim-vs-proof check
    def _remember_repos(self, username: str, raw_repos: list[dict]) -> None:
        mini = [
            {"name": r.get("name"), "fork": bool(r.get("fork")), "language": r.get("language"),
             "pushed_at": r.get("pushed_at"), "created_at": r.get("created_at"), "relevant": _is_relevant(r)}
            for r in raw_repos if r.get("name")
        ]
        self._repos[username.lower()] = mini
        self._disk["repos:" + username.lower()] = {"ts": time.time(), "data": mini}

    async def list_repos(self, username: str) -> list[dict]:
        key = username.lower()
        if key in self._repos:
            return self._repos[key]
        hit = self._disk.get("repos:" + key)
        if hit and time.time() - hit["ts"] < CACHE_TTL_S:
            self._repos[key] = hit["data"]
            return hit["data"]
        resp = await self._get(f"/users/{username}/repos", sort="pushed", per_page=100, type="owner")
        if resp.status_code == 200:
            self._remember_repos(username, resp.json())
        return self._repos.get(key, [])

    async def repo_evidence(self, owner: str, name: str) -> dict | None:
        """Evidence sources of one repo, labelled by origin (cached; None if unavailable):
        description/topics, README, dependency files (root and up to two folders down), and file/folder names."""
        key = f"{owner}/{name}".lower()
        if key in self._evidence:
            return self._evidence[key]
        hit = self._disk.get("evidence:" + key)
        if hit and time.time() - hit["ts"] < CACHE_TTL_S and "sources" in (hit["data"] or {}):
            self._evidence[key] = hit["data"]
            return hit["data"]
        result: dict | None = None
        try:
            meta = await self._get(f"/repos/{owner}/{name}")
            if meta.status_code == 200:
                m = meta.json()
                created, pushed = _parse(m.get("created_at")), _parse(m.get("pushed_at"))
                sources: dict[str, str] = {}
                desc = " ".join([m.get("description") or "", " ".join(m.get("topics") or [])]).strip()
                if desc:
                    sources["description/topics"] = desc
                raw = {"Accept": "application/vnd.github.raw+json"}
                has_readme = False
                async with self._sem:
                    resp = await self._client.get(f"/repos/{owner}/{name}/readme", headers=raw)
                if resp.status_code == 200:
                    has_readme = True
                    sources["README"] = resp.text[:20000]
                elif resp.status_code in (403, 429):
                    raise RateLimited("rate limited while reading README")
                paths: list[str] = []
                tree = await self._get(f"/repos/{owner}/{name}/git/trees/{m.get('default_branch') or 'HEAD'}", recursive=1)
                if tree.status_code == 200:
                    paths = [t["path"] for t in tree.json().get("tree", []) if t.get("path")]
                if paths:
                    sources["file names"] = paths_to_text(paths)
                for path in pick_manifest_paths(paths):
                    async with self._sem:
                        mr = await self._client.get(f"/repos/{owner}/{name}/contents/{path}", headers=raw)
                    if mr.status_code == 200:
                        sources[path] = mr.text[:20000]
                    elif mr.status_code in (403, 429):
                        raise RateLimited("rate limited while reading dependency files")
                result = {
                    "fork": bool(m.get("fork")), "has_readme": has_readme, "sources": sources,
                    "files_listed": len(paths), "manifests_read": [k for k in sources if k not in ("description/topics", "README", "file names")],
                    "active_span_days": (pushed - created).days if created and pushed else None,
                }
        except RateLimited:
            self._rate_limited = True
            return None
        except Exception as exc:  # network errors etc.: advisory feature, just no evidence
            log.warning("repo evidence failed for %s: %s", key, exc)
            return None
        self._evidence[key] = result
        if result:
            self._disk["evidence:" + key] = {"ts": time.time(), "data": result}
        return result

    async def _fetch(self, username: str) -> GitHubResult:
        res = GitHubResult(username=username)
        now = datetime.now(timezone.utc)
        try:
            repos_resp = await self._get(f"/users/{username}/repos", sort="pushed", per_page=100, type="owner")
            if repos_resp.status_code == 404:
                res.status, res.detail = "not_found", "GitHub user not found or profile private"
                res.summary = f"GitHub user '{username}' not found."
                return res
            if repos_resp.status_code != 200:
                res.status, res.detail = "error", f"HTTP {repos_resp.status_code}"
                res.summary = "GitHub lookup failed; scored 0 for GitHub."
                return res
            self._remember_repos(username, repos_resp.json())
            repos = [r for r in repos_resp.json() if not r.get("fork")]
            res.public_repos = len(repos)
            maintained_cut = now - timedelta(days=cfg.GITHUB_MAINTAINED_WINDOW_DAYS)
            recent_cut = now - timedelta(days=cfg.GITHUB_ACTIVITY_WINDOW_DAYS)
            pushed = [(_parse(r.get("pushed_at")), r) for r in repos]
            maintained = [r for t, r in pushed if t and t >= maintained_cut]
            res.maintained_repos = len(maintained)
            relevant = [r for r in maintained if _is_relevant(r)]
            res.relevant_repos = len(relevant)
            res.relevant_repo_names = [r["name"] for r in relevant[:5]]

            # recent public events (best effort: needs one more request)
            events = None
            if self.authenticated or (self._remaining or 0) > 15:
                try:
                    ev_resp = await self._get(f"/users/{username}/events/public", per_page=100)
                    if ev_resp.status_code == 200:
                        events = [e for e in ev_resp.json() if (_parse(e.get("created_at")) or now) >= recent_cut]
                except RateLimited:
                    res.detail = "events endpoint skipped (rate limit)"
            if events is not None:
                res.recent_events = len(events)
                n = len(events)
            else:  # derive activity from repo push times instead
                res.status = "partial"
                recent_repos = sum(1 for t, _ in pushed if t and t >= recent_cut)
                res.recent_events = None
                n = recent_repos * 5
                res.detail = res.detail or "events unavailable; activity estimated from repo push dates"
            res.activity_score = 0 if n == 0 else 2 if n < 5 else 3 if n < 15 else 4 if n < 30 else 5
            maint_pts = 0 if not maintained else 1 if len(maintained) < 4 else 2
            rel_pts = min(3, len(relevant))
            res.repo_score = min(5, maint_pts + rel_pts)
            res.score = res.activity_score + res.repo_score
            if res.status == "no_profile":
                res.status = "ok"
            res.summary = (
                f"{res.maintained_repos} repo(s) pushed in last 12 months, {res.relevant_repos} Python/AI-relevant"
                + (f" ({', '.join(res.relevant_repo_names[:3])})" if res.relevant_repo_names else "")
                + (f"; {res.recent_events} public events in last {cfg.GITHUB_ACTIVITY_WINDOW_DAYS}d" if res.recent_events is not None else "; activity estimated from push dates")
                + f". GitHub score {res.score}/10."
            )
        except RateLimited as exc:
            res.status, res.detail = "rate_limited", str(exc)
            res.summary = "GitHub API rate-limited; enrichment skipped (set GITHUB_TOKEN for a higher limit)."
        except Exception as exc:  # network errors, bad JSON, ...
            log.warning("GitHub enrichment failed for %s: %s", username, exc)
            res.status, res.detail = "error", f"{type(exc).__name__}: {exc}"
            res.summary = "GitHub enrichment failed; continued without it."
        return res


MANIFEST_NAMES = {"requirements.txt", "pyproject.toml", "package.json", "pipfile", "environment.yml", "setup.py"}
SKIP_DIRS = ("node_modules", "venv", ".venv", "site-packages", "vendor", "dist", "build", "__pycache__")
MAX_MANIFESTS = 4
MAX_PATHS_TEXT = 800


def _in_skipped_dir(path: str) -> bool:
    return any(part in SKIP_DIRS for part in path.split("/")[:-1])


def pick_manifest_paths(paths: list[str]) -> list[str]:
    """Dependency files at the repo root or up to two folders down (e.g. backend/requirements.txt), shallowest first."""
    found = [
        p for p in paths
        if p.rsplit("/", 1)[-1].lower() in MANIFEST_NAMES and p.count("/") <= 2
        and not _in_skipped_dir(p)
    ]
    return sorted(found, key=lambda p: (p.count("/"), p))[:MAX_MANIFESTS]


def paths_to_text(paths: list[str]) -> str:
    """File/folder names as searchable words ('CrewAI_Agents/app.py' -> 'CrewAI Agents app py')."""
    shown = [p for p in paths if not _in_skipped_dir(p)][:MAX_PATHS_TEXT]
    return " ".join(re.sub(r"[_\-./]+", " ", p) for p in shown)


def _parse(ts: str | None):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_relevant(repo: dict) -> bool:
    if (repo.get("language") or "").lower() == "python":
        return True
    blob = " ".join([repo.get("name") or "", repo.get("description") or "", " ".join(repo.get("topics") or [])])
    return bool(AI_REPO_HINT.search(blob))
