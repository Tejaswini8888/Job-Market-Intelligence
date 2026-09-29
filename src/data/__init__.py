"""Python data-access layer for the Job Market Intelligence platform.

Two modules live here:

* :mod:`src.data.database` - the PostgreSQL connection layer. It reads the
  settings from ``.env``, opens psycopg 3 connections, and can run a query and
  return a ``pandas.DataFrame``.
* :mod:`src.data.queries` - reusable analytics functions, one per dashboard
  need, all returning ``pandas.DataFrame``.

Typical use from a future dashboard or notebook::

    from src.data import get_top_skills, test_connection

    test_connection()          # raises if the database is unreachable
    top_skills = get_top_skills(limit=5)
"""

from __future__ import annotations

from src.data.database import (
    ConfigurationError,
    DatabaseConnectionError,
    connection_scope,
    describe_database_target,
    fetch_dataframe,
    get_connection,
    get_database_config,
    test_connection,
)
from src.data.queries import (
    get_all_companies,
    get_all_jobs,
    get_available_job_roles,
    get_average_salary_by_role,
    get_experience_distribution,
    get_job_counts_by_country,
    get_job_counts_by_role,
    get_job_counts_by_work_mode,
    get_jobs_by_company,
    get_jobs_by_industry,
    get_recent_jobs,
    get_required_skills_for_role,
    get_skill_catalog,
    get_table_row_counts,
    get_top_skills,
)

__all__ = [
    # database.py
    "ConfigurationError",
    "DatabaseConnectionError",
    "connection_scope",
    "describe_database_target",
    "fetch_dataframe",
    "get_connection",
    "get_database_config",
    "test_connection",
    # queries.py
    "get_all_companies",
    "get_all_jobs",
    "get_average_salary_by_role",
    "get_experience_distribution",
    "get_job_counts_by_country",
    "get_job_counts_by_role",
    "get_job_counts_by_work_mode",
    "get_jobs_by_company",
    "get_jobs_by_industry",
    "get_recent_jobs",
    "get_required_skills_for_role",
    "get_skill_catalog",
    "get_table_row_counts",
    "get_top_skills",
]
