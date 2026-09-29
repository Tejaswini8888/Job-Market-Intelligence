r"""Tests for the FastAPI backend (backend/).

The API talks to the same real local PostgreSQL database as the dashboard, so
the DB-backed tests use the exact skip pattern from ``test_database.py``:
nothing here contains a password (every setting comes from the environment),
and when PostgreSQL is unreachable the database tests are skipped with a
reason instead of failing::

    .\.venv\Scripts\Activate.ps1
    python -m pytest tests/test_api.py -v

The validation tests (malformed bodies, bounds on ``top_n``/``limit``, unknown
routes, sanitised database errors) run with NO database at all, so a CI job
without a database still exercises most of the behavioural contract.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import services
from backend.app.main import app
from src.data import queries
from src.data.database import (
    ConfigurationError,
    DatabaseConnectionError,
    test_connection as check_connection,
)

# ---------------------------------------------------------------------------
# Database reachability - identical pattern to tests/test_database.py
# ---------------------------------------------------------------------------


def _check_database() -> tuple[bool, str]:
    """Try to connect once. Returns ``(ok, reason)``.

    The reason string comes from the data-access layer, which never includes
    the password in its error messages.
    """
    try:
        result = check_connection()
    except (ConfigurationError, DatabaseConnectionError) as exc:
        return False, str(exc)
    except Exception as exc:  # driver-level failure of any other kind
        return False, f"{type(exc).__name__}: {exc}"
    return True, f"connected to {result.get('database')} as {result.get('user')}"


_DATABASE_AVAILABLE, _DATABASE_REASON = _check_database()


@pytest.fixture(scope="session")
def database() -> str:
    """Skip the test unless the local PostgreSQL database is reachable."""
    if not _DATABASE_AVAILABLE:
        pytest.skip(
            "These tests require a running local PostgreSQL database and "
            "DB_USER / DB_PASSWORD in .env. Reason: " + _DATABASE_REASON
        )
    return _DATABASE_REASON


@pytest.fixture(scope="module")
def client() -> TestClient:
    """A TestClient with the app's startup/shutdown lifespan applied."""
    with TestClient(app) as test_client:
        yield test_client


def _first_role_with_skills() -> str:
    """A role guaranteed to require at least one skill, else pytest fails."""
    roles = queries.get_available_job_roles()
    with_skills = roles[roles["skill_count"] > 0]
    assert not with_skills.empty, "seed data has no role with skill requirements"
    return str(with_skills.iloc[0]["role"])


# ---------------------------------------------------------------------------
# 1. No database needed: shape, validation, sanitised errors
# ---------------------------------------------------------------------------


def test_root_returns_service_metadata(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["app"]
    assert body["version"]
    assert body["health"] == "/health"
    assert body["docs"] == "/docs"


def test_unknown_route_returns_404(client: TestClient) -> None:
    assert client.get("/definitely-not-an-endpoint").status_code == 404


def test_skill_gap_missing_role_returns_422(client: TestClient) -> None:
    response = client.post("/skill-gap", json={"skills": ["Python"]})
    assert response.status_code == 422


def test_skill_gap_empty_skills_returns_422(client: TestClient) -> None:
    response = client.post("/skill-gap", json={"role": "Data Engineer", "skills": []})
    assert response.status_code == 422


def test_skill_gap_blank_skills_returns_422(client: TestClient) -> None:
    response = client.post(
        "/skill-gap", json={"role": "Data Engineer", "skills": ["   ", ""]}
    )
    assert response.status_code == 422


def test_recommend_empty_skills_returns_422(client: TestClient) -> None:
    response = client.post("/recommend", json={"skills": [], "top_n": 5})
    assert response.status_code == 422


def test_recommend_blank_skills_returns_422(client: TestClient) -> None:
    assert client.post("/recommend", json={"skills": ["  "]}).status_code == 422


def test_recommend_top_n_lower_bound_returns_422(client: TestClient) -> None:
    response = client.post("/recommend", json={"skills": ["Python"], "top_n": 0})
    assert response.status_code == 422


def test_recommend_top_n_upper_bound_returns_422(client: TestClient) -> None:
    response = client.post("/recommend", json={"skills": ["Python"], "top_n": 101})
    assert response.status_code == 422


def test_analytics_skills_limit_lower_bound_returns_422(client: TestClient) -> None:
    assert client.get("/analytics/skills", params={"limit": 0}).status_code == 422


def test_analytics_skills_limit_over_max_returns_422(client: TestClient) -> None:
    assert (
        client.get(
            "/analytics/skills", params={"limit": queries.MAX_LIMIT + 1}
        ).status_code
        == 422
    )


def test_database_error_returns_sanitized_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A DB failure must not leak internals; 503 with a clean message."""

    def boom(*_args, **_kwargs):
        raise DatabaseConnectionError("connection failed for host=... password=hunter2")

    monkeypatch.setattr(services.queries, "get_all_jobs", boom)
    response = client.get("/jobs")
    assert response.status_code == 503
    assert "hunter2" not in response.text
    assert "stack" not in response.text.lower()
    assert "unreachable" in response.json()["detail"]


def test_health_stays_ok_when_database_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/health must answer 200 even when PostgreSQL is unavailable."""

    def boom(*_args, **_kwargs):
        raise DatabaseConnectionError("no route to host")

    monkeypatch.setattr(services.queries, "get_table_row_counts", boom)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "unavailable"
    assert body["tables"] == {}


# ---------------------------------------------------------------------------
# 2. Database-backed: read-only endpoints
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("database")
def test_health_reports_database_up(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"
    assert body["tables"].get("jobs", 0) > 0


@pytest.mark.usefixtures("database")
def test_jobs_are_newest_first(client: TestClient) -> None:
    response = client.get("/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert jobs, "expected at least one posting"
    assert {"company_name", "job_title", "country", "salary_max"} <= set(jobs[0])
    dates = [job["posted_date"] for job in jobs]
    assert dates == sorted(dates, reverse=True), "postings must come newest first"


@pytest.mark.usefixtures("database")
def test_jobs_filter_by_country(client: TestClient) -> None:
    sample_country = str(queries.get_all_jobs().iloc[0]["country"])
    response = client.get("/jobs", params={"country": sample_country})
    assert response.status_code == 200
    jobs = response.json()
    assert jobs
    assert all(job["country"] == sample_country for job in jobs)


@pytest.mark.usefixtures("database")
def test_jobs_filter_by_job_role_is_case_insensitive(client: TestClient) -> None:
    role = _first_role_with_skills()
    response = client.get("/jobs", params={"job_role": role.lower()})
    assert response.status_code == 200
    jobs = response.json()
    assert jobs
    assert all(job["job_title"] == role for job in jobs)


@pytest.mark.usefixtures("database")
def test_jobs_no_result_when_filter_matches_nothing(client: TestClient) -> None:
    response = client.get("/jobs", params={"country": "Narnia"})
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.usefixtures("database")
def test_skills_endpoint_lists_catalog(client: TestClient) -> None:
    response = client.get("/skills")
    assert response.status_code == 200
    skills = response.json()
    assert skills
    assert {"skill_id", "skill_name", "skill_category"} <= set(skills[0])
    names = [skill["skill_name"] for skill in skills]
    assert names == sorted(names, key=str.casefold)


@pytest.mark.usefixtures("database")
def test_companies_endpoint_lists_employers(client: TestClient) -> None:
    response = client.get("/companies")
    assert response.status_code == 200
    companies = response.json()
    assert companies
    assert {"company_id", "company_name", "industry", "job_count"} <= set(companies[0])
    assert all(company["job_count"] >= 0 for company in companies)


@pytest.mark.usefixtures("database")
def test_analytics_skills_respects_limit(client: TestClient) -> None:
    response = client.get("/analytics/skills", params={"limit": 5})
    assert response.status_code == 200
    demand = response.json()
    assert len(demand) == 5
    assert all(0.0 <= skill["pct_of_all_jobs"] <= 100.0 for skill in demand)


@pytest.mark.usefixtures("database")
def test_analytics_salaries_grouped_by_currency_and_period(client: TestClient) -> None:
    response = client.get("/analytics/salaries")
    assert response.status_code == 200
    salaries = response.json()
    assert salaries, "expected at least one role with a disclosed salary"
    assert {"role", "currency", "salary_period", "avg_salary_midpoint"} <= set(
        salaries[0]
    )
    assert all(row["jobs_with_salary"] > 0 for row in salaries)


@pytest.mark.usefixtures("database")
def test_analytics_roles_reports_market_share(client: TestClient) -> None:
    response = client.get("/analytics/roles")
    assert response.status_code == 200
    roles = response.json()
    assert roles
    assert {"role", "job_count", "pct_of_all_jobs"} <= set(roles[0])
    assert sum(role["job_count"] for role in roles) == len(queries.get_all_jobs())


# ---------------------------------------------------------------------------
# 3. Database-backed: POST /skill-gap and POST /recommend
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("database")
def test_skill_gap_against_a_real_role(client: TestClient) -> None:
    role = _first_role_with_skills()
    response = client.post(
        "/skill-gap", json={"role": role, "skills": ["Python", "SQL"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == role
    assert 0.0 <= body["match_percentage"] <= 100.0
    assert set(body) == {
        "role",
        "match_percentage",
        "matched_skills",
        "missing_skills",
        "required_skills",
        "unknown_skills",
        "recognized_not_required",
    }
    statuses = body["matched_skills"] + body["missing_skills"]
    assert sorted(statuses, key=str.casefold) == sorted(
        body["required_skills"], key=str.casefold
    ), "matched + missing must partition the required skills"
    assert body["unknown_skills"] == []


@pytest.mark.usefixtures("database")
def test_skill_gap_reports_unknown_skills(client: TestClient) -> None:
    role = _first_role_with_skills()
    response = client.post(
        "/skill-gap", json={"role": role, "skills": ["DefinitelyNotARealSkill"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["unknown_skills"] == ["DefinitelyNotARealSkill"]
    assert body["matched_skills"] == []


@pytest.mark.usefixtures("database")
def test_skill_gap_unknown_role_returns_404(client: TestClient) -> None:
    response = client.post(
        "/skill-gap",
        json={"role": "Role That Does Not Exist", "skills": ["Python"]},
    )
    assert response.status_code == 404
    assert "unknown role" in response.json()["detail"].lower()


@pytest.mark.usefixtures("database")
def test_recommend_returns_ranked_roles(client: TestClient) -> None:
    response = client.post("/recommend", json={"skills": ["Python", "SQL"], "top_n": 3})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert 1 <= len(body["recommendations"]) <= 3
    assert "Python" in body["known_skills"]
    scores = [rec["score"] for rec in body["recommendations"]]
    assert scores == sorted(scores, reverse=True), "roles must be ranked by score"
    for rec in body["recommendations"]:
        assert 0.0 <= rec["score"] <= 100.0
        assert isinstance(rec["matched_skills"], list)
        assert isinstance(rec["required_count"], int)
    steps = " ".join(body["model"]["steps"])
    assert "Skill Similarity Score" in steps
    assert "prototype" in body["model"]["limitations"]


@pytest.mark.usefixtures("database")
def test_recommend_with_unknown_skills_explains(client: TestClient) -> None:
    response = client.post(
        "/recommend", json={"skills": ["DefinitelyNotARealSkill", "SQL"], "top_n": 5}
    )
    assert response.status_code == 200
    body = response.json()
    assert "DefinitelyNotARealSkill" in body["unknown_skills"]
    assert body["status"] == "ok"


@pytest.mark.usefixtures("database")
def test_recommend_top_n_larger_than_corpus_returns_all(client: TestClient) -> None:
    response = client.post("/recommend", json={"skills": ["Python", "SQL"], "top_n": 100})
    assert response.status_code == 200
    body = response.json()
    assert len(body["recommendations"]) == body["role_count"]


@pytest.mark.usefixtures("database")
def test_recommend_all_unknown_skills_explains_itself(client: TestClient) -> None:
    """Every skill outside the vocabulary must still get a clear answer."""
    response = client.post(
        "/recommend", json={"skills": ["NopeOne", "NopeTwo"], "top_n": 5}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "no_known_skills"
    assert body["recommendations"] == []
    assert body["message"]


@pytest.mark.usefixtures("database")
def test_skill_gap_and_skills_catalog_share_the_same_names(client: TestClient) -> None:
    """Matches must always come from the shared skill catalog."""
    catalog_names = {row["skill_name"] for row in client.get("/skills").json()}
    role = _first_role_with_skills()
    matched = client.post(
        "/skill-gap", json={"role": role, "skills": list(catalog_names)[:3]}
    ).json()
    assert set(matched["matched_skills"]).issubset(catalog_names)