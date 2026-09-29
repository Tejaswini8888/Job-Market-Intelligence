"""The FastAPI application: routes, CORS, and error handling.

The routes are intentionally thin - every one of them fetches a Pydantic
model from :mod:`backend.app.services` and returns it. No SQL, no DataFrame
handling, no recommender detail lives here. Interactive documentation is at
``/docs`` (Swagger) and ``/redoc``.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app import services
from backend.app.schemas import (
    Company,
    HealthResponse,
    Job,
    RecommendationRequest,
    RecommendationResponse,
    RoleAnalytics,
    RootInfo,
    SalaryAnalytics,
    Skill,
    SkillDemand,
    SkillGapRequest,
    SkillGapResponse,
)
from backend.app.services import RoleNotFoundError
from dashboard.components import redact
from src.data.database import ConfigurationError, DatabaseConnectionError
from src.data.queries import MAX_LIMIT

log = logging.getLogger("backend.api")

#: Interactive documentation lives side by side at these two paths.
docs_url = "/docs"

app = FastAPI(
    title="Job Market Intelligence API",
    version="0.1.0",
    summary="Analytics, Skill Gap and Role Recommendations over the job market.",
    description=(
        "REST front to the Job Market Intelligence platform. Every number here "
        "comes from the same PostgreSQL database and the same Python layers "
        "the Streamlit dashboard uses: analytics via ``src.data.queries``, the "
        "rule-based Skill Gap Analyzer via the dashboard's own component, and "
        "the role rankings via the TF-IDF recommender in ``ml/``. The "
        "recommender's ``score`` is a Skill Similarity Score, never a "
        "probability.\n\n"
        "Interactive docs: this page (Swagger) and ``/redoc``."
    ),
    docs_url=docs_url,
    redoc_url="/redoc",
)


# ---------------------------------------------------------------------------
# CORS - deliberately small: the local Streamlit dashboard and local tooling.
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8500",
        "http://127.0.0.1:8500",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    allow_credentials=False,
)


# ---------------------------------------------------------------------------
# Error handling - sanitised to the outside, detailed in the server log.
# ---------------------------------------------------------------------------


@app.exception_handler(DatabaseConnectionError)
@app.exception_handler(ConfigurationError)
async def _database_unavailable(_request, _exc) -> JSONResponse:
    """The data layer cannot do its one job; 503 with no internals exposed."""
    log.error("database query failed: %s", redact(_exc))
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "The database is unreachable right now. Please check that "
                "PostgreSQL is running and try again."
            )
        },
    )


@app.exception_handler(RoleNotFoundError)
async def _role_not_found(_request, exc: RoleNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"detail": f"Unknown role: '{exc.args[0]}'. No postings for it in the database."},
    )


@app.exception_handler(Exception)
async def _unexpected_error(_request, exc: Exception) -> JSONResponse:
    """Never leak a traceback or credentials; the console gets the detail."""
    log.exception("unhandled error serving a request: %s", redact(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."},
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_model=RootInfo, tags=["meta"])
def root() -> RootInfo:
    """Where this service lives and how to reach its two most useful pages."""
    return RootInfo(app=app.title, version=app.version)


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """Liveness probe; also answers whether PostgreSQL is reachable."""
    return services.health()


@app.get("/jobs", response_model=list[Job], tags=["data"])
def jobs(
    country: str | None = None,
    work_mode: str | None = None,
    employment_type: str | None = None,
    industry: str | None = None,
    job_role: str | None = None,
) -> list[Job]:
    """Every posting (newest first), optionally filtered by the query params."""
    return services.list_jobs(
        country=country,
        work_mode=work_mode,
        employment_type=employment_type,
        industry=industry,
        job_role=job_role,
    )


@app.get("/skills", response_model=list[Skill], tags=["data"])
def skills() -> list[Skill]:
    """Every skill the database knows about."""
    return services.list_skills()


@app.get("/companies", response_model=list[Company], tags=["data"])
def companies() -> list[Company]:
    """Every employer, with how many postings each currently has."""
    return services.list_companies()


@app.get("/analytics/skills", response_model=list[SkillDemand], tags=["analytics"])
def analytics_skills(
    limit: int = Query(default=10, ge=1, le=MAX_LIMIT, description="how many skills to return."),
) -> list[SkillDemand]:
    """The most-requested skills across all postings."""
    return services.top_skills(limit=limit)


@app.get("/analytics/salaries", response_model=list[SalaryAnalytics], tags=["analytics"])
def analytics_salaries() -> list[SalaryAnalytics]:
    """Average advertised salary per role, grouped by currency and period."""
    return services.salary_statistics()


@app.get("/analytics/roles", response_model=list[RoleAnalytics], tags=["analytics"])
def analytics_roles() -> list[RoleAnalytics]:
    """How much of the market each role accounts for."""
    return services.role_statistics()


@app.post("/skill-gap", response_model=SkillGapResponse, tags=["analysis"])
def skill_gap(request: SkillGapRequest) -> SkillGapResponse:
    """The dashboard's rule-based skill match for one role.

    Same calculation as the Skill Gap Analyzer tab: `match_percentage` is
    `matched required skills / total required skills * 100`, one decimal.
    """
    return services.analyse_skill_gap(request)


@app.post("/recommend", response_model=RecommendationResponse, tags=["analysis"])
def recommend(request: RecommendationRequest) -> RecommendationResponse:
    """Rank roles by Skill Similarity Score against the given skills.

    Uses the same TF-IDF recommender the dashboard's Role Recommendations tab
    shows, including its diagnostics (`status`, `known/unknown` skills, and
    the model facts) so an empty answer is never ambiguous.
    """
    return services.recommend_roles(request)