import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


import pytest  # noqa: E402


class _NoNetworkGitHub:
    def __init__(self, *a, **k):
        pass

    async def enrich(self, username):
        from resume_screener.models import GitHubResult

        return GitHubResult(username=username, status="error", detail="network disabled in tests") if username else GitHubResult()

    async def aclose(self):
        pass


@pytest.fixture(autouse=True)
def no_github_network(monkeypatch):
    monkeypatch.setattr("resume_screener.pipeline.GitHubEnricher", _NoNetworkGitHub)
