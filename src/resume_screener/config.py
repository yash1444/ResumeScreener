"""Settings, weights and thresholds. No business logic lives here."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

try:  # .env is a convenience, never a requirement
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

# Category maxima (sum = 100)
WEIGHTS = {
    "ai_project_depth": 40,
    "python_backend": 30,
    "cloud_fullstack": 15,
    "github": 10,
    "engineering_depth": 5,
}

# Points per capability inside the AI-depth category (maxima sum to 37, +3 multi-project bonus = 40)
AI_CAPABILITY_POINTS = {
    "llm_usage": 5,
    "prompting": 2,
    "retrieval": 9,
    "agents": 9,
    "state_workflow": 4,
    "evaluation": 5,
    "fine_tuning": 3,
}
AI_MULTI_PROJECT_BONUS = 3  # >=2 independent substantive AI projects
CLASSICAL_ML_AI_CAP = 12  # ML/CV-only profiles are eligible but capped
SKILLS_ONLY_FACTOR = 0.25  # keyword listed in a skills section but nowhere else

# Project-quality penalties (points deducted from AI depth)
PENALTY_ALL_THIN = 12
PENALTY_SOME_THIN = 5
PENALTY_TUTORIAL = 5
PENALTY_MAX = 15

# Python & backend points (sum = 30)
BACKEND_POINTS = {
    "python": 8,
    "web_framework": 6,
    "async": 4,
    "postgresql": 4,
    "redis": 4,
    "api_design": 2,
    "orm_tasks": 2,
}

# Cloud / deployment / full stack points (capped at 15)
CLOUD_POINTS = {"gcp": 5, "other_cloud": 3, "docker": 4, "kubernetes": 1, "ci_cd": 2, "frontend": 3}

# How far the LLM may move a rule-based category score (explainability guard-rail)
LLM_MAX_DELTA = {
    "ai_project_depth": 6,
    "python_backend": 4,
    "cloud_fullstack": 3,
    "engineering_depth": 1,
}

# GitHub scoring
GITHUB_ACTIVITY_WINDOW_DAYS = 90
GITHUB_MAINTAINED_WINDOW_DAYS = 365


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY") or None)
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    github_token: str | None = field(default_factory=lambda: os.getenv("GITHUB_TOKEN") or None)
    llm_concurrency: int = field(default_factory=lambda: int(os.getenv("LLM_CONCURRENCY", "5")))
    github_concurrency: int = field(default_factory=lambda: int(os.getenv("GITHUB_CONCURRENCY", "5")))
    llm_timeout_s: float = 60.0
    github_timeout_s: float = 15.0
    max_resume_chars: int = 14000
    llm_cache_enabled: bool = True  # reuse stored LLM answers for identical input (.cache/llm.json)
    second_opinion_enabled: bool = True  # LLM second opinion on borderline eligibility (advisory, never overrides rules)
    allow_classical_ml: bool = False  # True: ML/CV-only profiles become eligible (AI depth capped at 12/40)


# Claim-vs-proof (resume claims checked against public GitHub repos). Bonus only, never a penalty.
CLAIM_BONUS_MAX = 3  # added to ai_project_depth (still capped at 40)
CLAIM_MIN_CLAIMS = 3  # need at least this many verifiable claims before a bonus can apply
MAX_CLAIM_REPOS = 3  # repos inspected per candidate
VERIFIABLE_TECHS = [
    "LangChain", "LangGraph", "LlamaIndex", "Google ADK", "CrewAI", "AutoGen", "MCP", "FastAPI", "Django", "Flask",
    "PostgreSQL", "Redis", "Celery", "Kafka", "Docker", "Kubernetes", "OpenAI", "Gemini", "Claude", "Vector Search",
    "Embeddings", "RAG", "Streamlit", "Pydantic", "Neo4j", "Hugging Face", "PyTorch", "TensorFlow",
]
