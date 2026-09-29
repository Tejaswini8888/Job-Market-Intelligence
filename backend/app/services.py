"""Service functions for the FastAPI backend.

These are the layer between the routes and the rest of the platform. They hold
no HTTP details: a route calls one function, gets a Pydantic model (or a list
of them) back, and returns it. All SQL lives in ``src.data.queries``, the
rule-based Skill Gap Analyzer is the dashboard's own
:func:`dashboard.components.analyze_skill_gap`, and the recommender is
``ml.recommender`` - nothing is reimplemented here.

Errors raised here fall into two buckets:

* :class:`RoleNotFoundError` - a known-nothing-about role the caller asked to
  analyse. The route maps it to 404.
* database-layer exceptions (:class:`src.data.database.DatabaseConnectionError`
  and friends) - mapped to a sanitised 503 by the app's exception handlers.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from backend.app.schemas import (
    Company,
    HealthResponse,
    Job,
    RoleAnalytics,
    RoleRecommendation,
    SalaryAnalytics,
    Skill,
    SkillDemand,
    SkillGapRequest,
    SkillGapResponse,
    RecommendationRequest,
    RecommendationResponse,
)
from dashboard.components import analyze_skill_gap
from ml.recommender import load_role_profiles, recommend_with_diagnostics
from src.data import queries
from src.data.database import ConfigurationError, DatabaseConnectionError

#: Maps the API's job-filter query names to their columns in ``get_all_jobs``.
_FILTER_TO_COLUMN: dict[str, str] = {
    "country": "country",
    "work_mode": "work_mode",
    "employment_type": "employment_type",
    "industry": "industry",
    "job_role": "job_title",
}


class RoleNotFoundError(Exception):
    """The requested role has no postings in the database."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scalar(value: object) -> object:
    """Turn any pandas ``NaN``/``NaT`` into ``None``; leave everything else alone."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    """Rows of a DataFrame as plain dicts, with ``NaN`` replaced by ``None``.

    Pydantic models are declared with ``... | None`` fields, but pandas hands
    back ``NaN``/``NaT`` objects that have no JSON representation. Normalising
    here means the models and the JSON response never see a ``NaN``.
    """
    rows = frame.to_dict("records")
    if not rows:
        return rows
    return [{key: _scalar(value) for key, value in row.items()} for row in rows]


def _filtered_jobs(filters: dict[str, str | None]) -> list[dict[str, Any]]:
    """``get_all_jobs()`` filtered by the caller's optional criteria.

    Filtering is done in pandas over the already-fetched frame, not in SQL:
    ``get_all_jobs`` has no filter arguments, the values are never pasted into
    SQL, and the comparisons are case-insensitive so ``"data scientist"``
    finds ``"Data Scientist"``. An unset filter matches everything.
    """
    frame = queries.get_all_jobs()
    for name, value in filters.items():
        if value is None:
            continue
        column = _FILTER_TO_COLUMN[name]
        frame = frame[frame[column].astype(str).str.casefold().eq(value.strip().casefold())]
    return _records(frame)


# ---------------------------------------------------------------------------
# Read-only endpoints
# ---------------------------------------------------------------------------


def health() -> HealthResponse:
    """The API is up; probe PostgreSQL for its table row counts if it replies."""
    try:
        counts = queries.get_table_row_counts()
    except (ConfigurationError, DatabaseConnectionError):
        return HealthResponse(status="ok", database="unavailable")
    except Exception:
        return HealthResponse(status="ok", database="unavailable")
    tables = {
        str(row["table_name"]): int(row["row_count"]) for row in _records(counts)
    }
    return HealthResponse(status="ok", database="up", tables=tables)


def list_jobs(
    country: str | None = None,
    work_mode: str | None = None,
    employment_type: str | None = None,
    industry: str | None = None,
    job_role: str | None = None,
) -> list[Job]:
    """Every posting, newest first, optionally narrowed by the given criteria."""
    filters = {
        "country": country,
        "work_mode": work_mode,
        "employment_type": employment_type,
        "industry": industry,
        "job_role": job_role,
    }
    return [Job(**row) for row in _filtered_jobs(filters)]


def list_skills() -> list[Skill]:
    """Every skill the database knows about, alphabetically."""
    return [Skill(**row) for row in _records(queries.get_skill_catalog())]


def list_companies() -> list[Company]:
    """Every employer, alphabetically, with its posting count."""
    return [Company(**row) for row in _records(queries.get_all_companies())]


def top_skills(limit: int) -> list[SkillDemand]:
    """The most-requested skills market-wide, up to ``limit``."""
    return [SkillDemand(**row) for row in _records(queries.get_top_skills(limit=limit))]


def salary_statistics() -> list[SalaryAnalytics]:
    """Average advertised salary per role, grouped by currency and period."""
    return [
        SalaryAnalytics(**row)
        for row in _records(queries.get_average_salary_by_role())
    ]


def role_statistics() -> list[RoleAnalytics]:
    """How much of the market each role accounts for."""
    return [
        RoleAnalytics(**row)
        for row in _records(queries.get_job_counts_by_role())
    ]


# ---------------------------------------------------------------------------
# POST /skill-gap
# ---------------------------------------------------------------------------


def analyse_skill_gap(request: SkillGapRequest) -> SkillGapResponse:
    """Compare one role's requirements with the user's skills.

    This is the dashboard's own rule-based calculation, called unchanged, so
    ``match_percentage`` here is exactly what the Skill Gap Analyzer tab shows.
    """
    required = queries.get_required_skills_for_role(request.role)
    if required.empty:
        raise RoleNotFoundError(request.role)

    catalog = queries.get_skill_catalog()
    result = analyze_skill_gap(
        required_skills=required,
        user_skills=", ".join(request.skills),
        catalog=catalog,
        role=request.role,
    )

    return SkillGapResponse(
        role=result.role,
        match_percentage=round(float(result.skill_match_pct), 1),
        matched_skills=list(result.matched["skill_name"]),
        missing_skills=list(result.missing["skill_name"]),
        required_skills=list(result.required["skill_name"]),
        unknown_skills=list(result.unrecognized),
        recognized_not_required=list(result.recognized_not_required),
    )


# ---------------------------------------------------------------------------
# POST /recommend
# ---------------------------------------------------------------------------


def recommend_roles(request: RecommendationRequest) -> RecommendationResponse:
    """Rank roles by Skill Similarity Score and attach the diagnostics.

    The ranking is :func:`ml.recommender.recommend_with_diagnostics` run
    unchanged; ``score`` stays the model's Skill Similarity Score and is never
    relabelled as a probability.
    """
    diagnostics = recommend_with_diagnostics(request.skills, top_n=request.top_n)
    results = diagnostics["results"]

    recommendations: list[RoleRecommendation] = []
    for row in _records(results):
        recommendations.append(
            RoleRecommendation(
                role=str(row["role"]),
                score=float(row["score"]),
                matched_skills=list(row["matched_skills"]),
                missing_skills=list(row["missing_skills"]),
                required_skills=list(row["required_skills"]),
                matched_count=int(row["matched_count"]),
                missing_count=int(row["missing_count"]),
                required_count=int(row["required_count"]),
                rule_based_pct=float(row["rule_based_pct"]),
                job_count=int(row["job_count"]),
            )
        )

    return RecommendationResponse(
        status=str(diagnostics["status"]),
        message=str(diagnostics["message"]),
        role_count=int(diagnostics["role_count"]),
        vocabulary_size=int(diagnostics["vocabulary_size"]),
        known_skills=list(diagnostics["known"]),
        unknown_skills=list(diagnostics["unknown"]),
        recommendations=recommendations,
        model=dict(diagnostics["info"]),
    )


# Kept importable for type-checkers and future callers, and so the layer's
# dependency on the ML layer is stated in one place.
__all__ = [
    "Company",
    "Job",
    "RecommendationRequest",
    "RecommendationResponse",
    "RoleAnalytics",
    "RoleNotFoundError",
    "RoleRecommendation",
    "SalaryAnalytics",
    "Skill",
    "SkillDemand",
    "SkillGapRequest",
    "SkillGapResponse",
    "analyse_skill_gap",
    "health",
    "list_companies",
    "list_jobs",
    "list_skills",
    "load_role_profiles",
    "recommend_roles",
    "role_statistics",
    "salary_statistics",
    "top_skills",
]