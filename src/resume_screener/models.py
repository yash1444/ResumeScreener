"""Typed data structures shared across the pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- ingestion
@dataclass
class RawResume:
    path: str
    filename: str
    text: str
    links: list[str] = field(default_factory=list)
    sha256: str = ""
    alt_text: str = ""  # same page text re-ordered by block position (top-to-bottom, left-to-right)


@dataclass
class ResumeSections:
    """Resume text split into logical sections. `evidence` excludes skills lists,
    education and certifications so that keyword-only claims are not mistaken for work."""

    sections: dict[str, str]
    evidence: str  # projects + experience + summary + unlabelled text
    skills: str
    sectioned: bool  # False when no headings could be detected


@dataclass
class Block:
    """One project / job entry (title line + bullets)."""

    text: str
    capabilities: dict[str, list[str]] = field(default_factory=dict)  # capability -> matched terms
    is_ai: bool = False
    is_ml_only: bool = False
    thin: bool = False
    owned: bool = False


@dataclass
class CandidateProfile:
    filename: str
    name: str
    name_confident: bool
    email: Optional[str]
    github_username: Optional[str]
    github_url: Optional[str]
    skills: list[str]
    sections: ResumeSections
    raw_text: str
    reordered: bool = False  # True when the geometric reading order gave clearly better sections


# ---------------------------------------------------------------- eligibility
class EligibilityResult(BaseModel):
    candidate: str
    eligible: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    python_evidence: list[str] = Field(default_factory=list)
    ai_evidence: list[str] = Field(default_factory=list)
    ai_evidence_level: str = "none"  # none | classical_ml | llm_agentic
    borderline_reasons: list[str] = Field(default_factory=list)  # non-empty -> eligible for an LLM second opinion


# ---------------------------------------------------------------- LLM schema
class CategoryJudgement(BaseModel):
    score: int = Field(ge=0, description="Points awarded for this category")
    evidence: list[str] = Field(default_factory=list, description="Short quotes/paraphrases from the resume (<=25 words each)")


class LLMAnalysis(BaseModel):
    candidate_name: str
    ai_project_depth: CategoryJudgement
    python_backend: CategoryJudgement
    cloud_fullstack: CategoryJudgement
    engineering_depth: CategoryJudgement
    thin_wrapper_projects: list[str] = Field(default_factory=list)
    tutorial_style_projects: list[str] = Field(default_factory=list)
    penalty: int = Field(default=0, ge=0, le=15, description="Deduction for shallow AI projects (0 if none)")
    project_summary: str
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)


class EligibilityOpinion(BaseModel):
    """LLM second opinion on the two eligibility questions. Advisory only: it can flag, never decide."""

    python_is_genuine: bool = Field(description="Python is a real skill/implementation language of this candidate, not an incidental mention")
    python_evidence: str = Field(description="Short quote (<=25 words) or 'none'")
    builds_with_llm_or_agents: bool = Field(
        description="The candidate BUILT or integrated an LLM / RAG / embeddings / agentic system. "
        "False for merely using AI tools (Copilot, ChatGPT, Claude Code) to write their own code, and for classical ML/CV only."
    )
    ai_evidence: str = Field(description="Short quote (<=25 words) or 'none'")
    confidence: Literal["low", "medium", "high"]
    reasoning: str = Field(description="One or two sentences")


# ---------------------------------------------------------------- GitHub
class GitHubResult(BaseModel):
    username: Optional[str] = None
    status: str = "no_profile"  # no_profile | ok | partial | not_found | rate_limited | error
    detail: str = ""
    recent_events: Optional[int] = None
    public_repos: Optional[int] = None
    maintained_repos: Optional[int] = None
    relevant_repos: Optional[int] = None
    relevant_repo_names: list[str] = Field(default_factory=list)
    activity_score: int = 0
    repo_score: int = 0
    score: int = 0
    summary: str = "No GitHub profile found in resume."


# ---------------------------------------------------------------- scoring
class ScoreBreakdown(BaseModel):
    ai_project_depth: int = 0
    python_backend: int = 0
    cloud_fullstack: int = 0
    github: int = 0
    engineering_depth: int = 0


class CandidateResult(BaseModel):
    rank: Optional[int] = None
    candidate_name: str
    filename: str
    email: Optional[str] = None
    eligible: bool
    total_score: Optional[int] = None
    score_breakdown: Optional[ScoreBreakdown] = None
    penalties: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    project_summary: str = ""
    github_summary: str = ""
    github: Optional[GitHubResult] = None
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    evidence: dict[str, list[str]] = Field(default_factory=dict)
    rejection_reasons: list[str] = Field(default_factory=list)
    claim_verification: Optional[dict] = None  # resume claims vs public GitHub repos (advisory)
    eligibility_check: Optional[dict] = None  # set only for borderline cases (see pipeline._eligibility_check)
    scoring_method: str = ""  # rules | rules+llm
    notes: list[str] = Field(default_factory=list)
