"""Pydantic request and response models for the FastAPI backend.

One purpose: make the API contract explicit. Every endpoint declares its
request and response type here, so the Swagger docs at ``/docs`` and the
validation at the edge are generated from the same source of truth.

Two conventions:

* Optional database columns are ``... | None``, so a missing value produces
  ``null`` in JSON instead of a ``NaN`` that has no JSON representation.
* The recommender's ``score`` is always labelled a "Skill Similarity Score" -
  a cosine-similarity figure between 0 and 100, never a probability.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator

from ml.recommender import DEFAULT_TOP_N


def _non_blank_string(value: str) -> str:
    """Strip an incoming string and reject one that is all whitespace."""
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("must not be blank.")
    return cleaned


def _clean_skills(values: list[str]) -> list[str]:
    """Strip each skill and reject a list with no usable entries."""
    cleaned = [skill.strip() for skill in values if skill.strip()]
    if not cleaned:
        raise ValueError("provide at least one skill.")
    return cleaned


# ---------------------------------------------------------------------------
# GET /identity and GET /health
# ---------------------------------------------------------------------------


class RootInfo(BaseModel):
    """What this service is and where to find its essentials."""

    app: str
    version: str
    docs: str = "/docs"
    health: str = "/health"


class HealthResponse(BaseModel):
    """Liveness of the API plus a cheap probe of the PostgreSQL database."""

    status: str
    database: str = Field(
        ...,
        description='"up" when PostgreSQL answered the health query, else "unavailable".',
    )
    tables: dict[str, int] = Field(
        default_factory=dict,
        description="row count per core table when the database is reachable.",
    )


# ---------------------------------------------------------------------------
# GET /jobs, /skills, /companies
# ---------------------------------------------------------------------------


class Job(BaseModel):
    """One job posting joined with its employer's details."""

    job_id: int
    company_id: int
    company_name: str
    industry: str
    job_title: str
    location: str | None = None
    country: str | None = None
    employment_type: str | None = None
    work_mode: str | None = None
    experience_min: int | None = None
    experience_max: int | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str | None = None
    salary_period: str | None = None
    posted_date: date | None = None


class Skill(BaseModel):
    """One skill the database knows about, as defined by the ``skills`` table."""

    skill_id: int
    skill_name: str
    skill_category: str


class SkillDemand(Skill):
    """A skill together with how widely it appears across postings."""

    job_count: int
    company_count: int
    pct_of_all_jobs: float


class Company(BaseModel):
    """One employer and how many postings are currently attributed to it."""

    company_id: int
    company_name: str
    industry: str
    company_size: str | None = None
    headquarters: str | None = None
    job_count: int


# ---------------------------------------------------------------------------
# GET /analytics/*
# ---------------------------------------------------------------------------


class RoleAnalytics(BaseModel):
    """How much of the market each job title (role) accounts for."""

    role: str
    job_count: int
    company_count: int
    pct_of_all_jobs: float


class SalaryAnalytics(BaseModel):
    """Advertised salary statistics for one role in one currency/period.

    Averages are grouped by ``currency`` and ``salary_period`` on purpose:
    the database has no exchange-rate table, so averaging INR with USD - or a
    yearly figure with an hourly one - would be meaningless.
    """

    role: str
    currency: str
    salary_period: str
    jobs_with_salary: int
    company_count: int
    avg_salary_min: float
    avg_salary_max: float
    avg_salary_midpoint: float
    lowest_salary_min: float
    highest_salary_max: float


# ---------------------------------------------------------------------------
# POST /skill-gap
# ---------------------------------------------------------------------------


class SkillGapRequest(BaseModel):
    """A target role and the skills the user already has.

    ``skills`` mirrors the dashboard's free-text field one item per box per
    skill. The rule-based comparison is identical to the dashboard's: the same
    :func:`dashboard.components.analyze_skill_gap` function is called, so the
    API and the UI can never disagree about a match percentage.
    """

    role: str = Field(..., min_length=1, description="job title as stored, e.g. 'Data Scientist'.")
    skills: list[str] = Field(
        ...,
        min_length=1,
        description="skills the user already has, one element per skill.",
    )

    @field_validator("role")
    @classmethod
    def _role_not_blank(cls, value: str) -> str:
        return _non_blank_string(value)

    @field_validator("skills")
    @classmethod
    def _skills_not_blank(cls, value: list[str]) -> list[str]:
        return _clean_skills(value)


class SkillGapResponse(BaseModel):
    """The match between a role and the user's skills.

    ``match_percentage`` is the same number the dashboard displays:
    ``100 * matched / required`` (0.0 when the role has no recorded skills),
    rounded to one decimal place. ``unknown_skills`` are the typed skills the
    database has never heard of; they are reported but never counted.
    """

    role: str
    match_percentage: float = Field(
        ...,
        description="matched required skills / total required skills * 100 (one decimal).",
    )
    matched_skills: list[str]
    missing_skills: list[str]
    required_skills: list[str]
    unknown_skills: list[str]
    recognized_not_required: list[str] = Field(
        ...,
        description="known skills the user listed that this role does not require.",
    )


# ---------------------------------------------------------------------------
# POST /recommend
# ---------------------------------------------------------------------------


class RecommendationRequest(BaseModel):
    """A skill list and how many ranked roles to return."""

    skills: list[str] = Field(
        ...,
        min_length=1,
        description="skills to rank roles against, one element per skill.",
    )
    top_n: int = Field(
        default=DEFAULT_TOP_N,
        ge=1,
        le=100,
        description=f"how many roles to return (default {DEFAULT_TOP_N}).",
    )

    @field_validator("skills")
    @classmethod
    def _skills_not_blank(cls, value: list[str]) -> list[str]:
        return _clean_skills(value)


class RoleRecommendation(BaseModel):
    """One ranked role from the recommender.

    ``score`` is the **Skill Similarity Score**: TF-IDF cosine similarity
    between the user's skill document and the role's profile, expressed on a
    0-100 scale. It is a geometric similarity, not a forecast, and never a
    probability.
    """

    role: str
    score: float = Field(..., description="Skill Similarity Score (0-100, not a probability).")
    matched_skills: list[str]
    missing_skills: list[str]
    required_skills: list[str]
    matched_count: int
    missing_count: int
    required_count: int
    rule_based_pct: float
    job_count: int


class RecommendationResponse(BaseModel):
    """Ranked roles plus the diagnostics needed to read them honestly.

    ``status`` uses the recommender's own vocabulary: ``ok``, ``no_roles``,
    ``no_skills`` or ``no_known_skills``. A non-``ok`` status means an empty
    ``recommendations`` list, and ``message`` explains why, so an empty result
    is informative rather than ambiguous.
    """

    status: str
    message: str
    role_count: int
    vocabulary_size: int
    known_skills: list[str] = Field(
        ..., description="typed skills recognised by the model, in the user's own spelling."
    )
    unknown_skills: list[str] = Field(
        ..., description="typed skills absent from the model's vocabulary, in the user's spelling."
    )
    recommendations: list[RoleRecommendation]
    model: dict[str, Any] = Field(
        ...,
        description="transparency notes: what the score is, and its documented limitations.",
    )