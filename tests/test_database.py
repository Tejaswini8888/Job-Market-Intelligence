r"""Tests for the PostgreSQL data-access layer.

These tests talk to a REAL local PostgreSQL database, because that is the
thing being verified. Nothing here contains a password: every setting comes
from the environment (``.env`` / ``DB_*`` variables).

If PostgreSQL is not reachable, or ``DB_USER`` / ``DB_PASSWORD`` are not
filled in, the database tests are SKIPPED with a reason instead of failing,
and the pure-validation tests still run::

    .\.venv\Scripts\Activate.ps1
    python -m pytest -v

To run them, create the local secret file first::

    copy .env.example .env      # then fill in DB_PASSWORD
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.data import queries

# NOTE: test_connection is imported as check_connection on purpose. pytest
# collects any module-level callable whose name starts with "test_", so the
# import alias stops it from trying to run our connection helper as a test.
from src.data.database import (
    ConfigurationError,
    DatabaseConnectionError,
    describe_database_target,
    fetch_dataframe,
    get_database_config,
)
from src.data.database import test_connection as check_connection

# ---------------------------------------------------------------------------
# Credentials come from the environment only. If they are missing, the database
# tests below are skipped rather than reported as failures.
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


# ---------------------------------------------------------------------------
# 1. The connection itself
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("database")
def test_database_connection_works(database: str) -> None:
    """A connection can be opened and a trivial query can be run on it."""
    result = check_connection()

    assert result["connected"] is True
    assert result["database"] == get_database_config()["DB_NAME"]
    assert result["user"] == get_database_config()["DB_USER"]
    assert result["server_version"], "PostgreSQL did not report a server version"
    assert database  # the fixture only returns after a successful connection


@pytest.mark.usefixtures("database")
def test_connection_is_read_only(database: str) -> None:
    """The data-access layer must not be able to modify the database."""
    frame = fetch_dataframe(
        "SELECT current_setting('default_transaction_read_only') AS read_only"
    )
    assert str(frame["read_only"].iloc[0]).lower() in {"on", "true"}


@pytest.mark.usefixtures("database")
def test_connection_details_never_expose_the_password(database: str) -> None:
    """The safe summary must not hand out the password."""
    config = get_database_config()
    summary = describe_database_target()

    assert "DB_PASSWORD" not in summary
    assert "password" not in summary
    assert summary["password_configured"] is True
    # The password must never appear as a value of the summary.
    assert config["DB_PASSWORD"] not in [str(value) for value in summary.values()]


# ---------------------------------------------------------------------------
# 2-5. The core tables
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("database")
def test_jobs_table_can_be_queried(database: str) -> None:
    """The jobs table exists, is readable, and holds the seeded postings."""
    frame = fetch_dataframe(
        """
        SELECT job_id, company_id, job_title, country, work_mode, posted_date
        FROM jobs
        ORDER BY job_id
        """
    )

    assert isinstance(frame, pd.DataFrame)
    assert list(frame.columns) == [
        "job_id",
        "company_id",
        "job_title",
        "country",
        "work_mode",
        "posted_date",
    ]
    assert not frame.empty, "jobs table is empty - load database/seed.sql"


@pytest.mark.usefixtures("database")
def test_companies_table_can_be_queried(database: str) -> None:
    """The companies table exists, is readable, and holds the seeded employers."""
    frame = fetch_dataframe(
        """
        SELECT company_id, company_name, industry, company_size, headquarters
        FROM companies
        ORDER BY company_id
        """
    )

    assert isinstance(frame, pd.DataFrame)
    assert list(frame.columns) == [
        "company_id",
        "company_name",
        "industry",
        "company_size",
        "headquarters",
    ]
    assert not frame.empty, "companies table is empty - load database/seed.sql"
    assert frame["company_name"].is_unique


@pytest.mark.usefixtures("database")
def test_skills_table_can_be_queried(database: str) -> None:
    """The skills table exists, is readable, and holds the seeded skills."""
    frame = fetch_dataframe(
        "SELECT skill_id, skill_name, skill_category FROM skills ORDER BY skill_id"
    )

    assert isinstance(frame, pd.DataFrame)
    assert list(frame.columns) == ["skill_id", "skill_name", "skill_category"]
    assert not frame.empty, "skills table is empty - load database/seed.sql"


@pytest.mark.usefixtures("database")
def test_job_skills_table_can_be_queried(database: str) -> None:
    """The jobs <-> skills junction table is readable and consistent."""
    counts = fetch_dataframe(
        """
        SELECT
            (SELECT COUNT(*) FROM companies) AS companies,
            (SELECT COUNT(*) FROM jobs)     AS jobs,
            (SELECT COUNT(*) FROM skills)   AS skills,
            (SELECT COUNT(*) FROM job_skills) AS job_skills
        """
    ).iloc[0]

    assert int(counts["companies"]) > 0
    assert int(counts["jobs"]) > 0
    assert int(counts["skills"]) > 0
    assert int(counts["job_skills"]) > 0

    # Every job_skills row must point at a real job and a real skill.
    orphans = fetch_dataframe(
        """
        SELECT COUNT(*) AS orphan_links
        FROM job_skills js
        LEFT JOIN jobs j   ON j.job_id   = js.job_id
        LEFT JOIN skills s ON s.skill_id = js.skill_id
        WHERE j.job_id IS NULL OR s.skill_id IS NULL
        """
    )
    assert int(orphans["orphan_links"].iloc[0]) == 0


# ---------------------------------------------------------------------------
# 6. The query functions return pandas DataFrames
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("database")
def test_query_function_returns_pandas_dataframe(database: str) -> None:
    """get_all_jobs() returns a DataFrame that matches the jobs table."""
    frame = queries.get_all_jobs()
    total_jobs = int(
        fetch_dataframe("SELECT COUNT(*) AS job_count FROM jobs")["job_count"].iloc[0]
    )

    assert isinstance(frame, pd.DataFrame)
    assert len(frame) == total_jobs
    for column in (
        "job_id",
        "company_name",
        "industry",
        "job_title",
        "country",
        "work_mode",
        "posted_date",
    ):
        assert column in frame.columns, f"missing column: {column}"
    assert frame["posted_date"].is_monotonic_decreasing


@pytest.mark.usefixtures("database")
def test_all_query_functions_return_dataframes(database: str) -> None:
    """Every function in queries.py returns a DataFrame, with no fake rows."""
    company_name = str(
        fetch_dataframe("SELECT company_name FROM companies ORDER BY company_id LIMIT 1")[
            "company_name"
        ].iloc[0]
    )
    industry = str(
        fetch_dataframe("SELECT industry FROM companies ORDER BY company_id LIMIT 1")[
            "industry"
        ].iloc[0]
    )

    results = {
        "get_all_jobs": queries.get_all_jobs(),
        "get_job_counts_by_role": queries.get_job_counts_by_role(),
        "get_job_counts_by_country": queries.get_job_counts_by_country(),
        "get_job_counts_by_work_mode": queries.get_job_counts_by_work_mode(),
        "get_top_skills": queries.get_top_skills(limit=10),
        "get_jobs_by_company": queries.get_jobs_by_company(company_name),
        "get_average_salary_by_role": queries.get_average_salary_by_role(),
        "get_jobs_by_industry": queries.get_jobs_by_industry(),
        "get_jobs_by_industry_filtered": queries.get_jobs_by_industry(industry),
        "get_experience_distribution": queries.get_experience_distribution(),
        "get_recent_jobs": queries.get_recent_jobs(limit=10),
        "get_table_row_counts": queries.get_table_row_counts(),
    }

    for name, frame in results.items():
        assert isinstance(frame, pd.DataFrame), f"{name} did not return a DataFrame"
        assert not frame.empty, f"{name} returned no rows"

    assert len(results["get_recent_jobs"]) == 10
    assert len(results["get_top_skills"]) == 10
    assert (
        results["get_job_counts_by_role"]["job_count"].sum()
        == len(results["get_all_jobs"])
    )
    assert results["get_jobs_by_company"]["company_name"].str.lower().eq(
        company_name.lower()
    ).all()


@pytest.mark.usefixtures("database")
def test_limit_argument_is_parameterised(database: str) -> None:
    """LIMIT is bound as a parameter, so it can only ever change the row count."""
    assert len(queries.get_top_skills(limit=3)) == 3
    assert len(queries.get_recent_jobs(limit=1)) == 1


@pytest.mark.usefixtures("database")
def test_sql_injection_attempt_is_treated_as_plain_text(database: str) -> None:
    """A caller-supplied value is bound as data, never executed as SQL."""
    malicious = "'; DROP TABLE jobs; --"

    assert queries.get_jobs_by_company(malicious).empty
    # The jobs table must still be there and still populated.
    remaining = int(
        fetch_dataframe("SELECT COUNT(*) AS job_count FROM jobs")["job_count"].iloc[0]
    )
    assert remaining > 0


# ---------------------------------------------------------------------------
# 7. Argument validation - needs no database, so it always runs
# ---------------------------------------------------------------------------


def test_invalid_limits_are_rejected() -> None:
    """A bad limit fails immediately with a clear error, before any SQL runs."""
    with pytest.raises(TypeError):
        queries.get_top_skills(limit="ten")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        queries.get_top_skills(limit=0)
    with pytest.raises(ValueError):
        queries.get_recent_jobs(limit=queries.MAX_LIMIT + 1)


def test_blank_lookup_values_are_rejected() -> None:
    """Blank company / industry input is rejected instead of matching everything."""
    with pytest.raises(ValueError):
        queries.get_jobs_by_company("   ")
    with pytest.raises(ValueError):
        queries.get_jobs_by_industry("")
    with pytest.raises(TypeError):
        queries.get_jobs_by_company(42)  # type: ignore[arg-type]


def test_environment_configuration_is_documented() -> None:
    """.env.example lists exactly the variables database.py requires."""
    from pathlib import Path

    from src.data.database import REQUIRED_ENV_VARS

    example = Path(__file__).resolve().parents[1] / ".env.example"
    assert example.exists(), ".env.example is missing"
    text = example.read_text(encoding="utf-8")
    for name in REQUIRED_ENV_VARS:
        assert f"{name}=" in text, f"{name} is not documented in .env.example"
