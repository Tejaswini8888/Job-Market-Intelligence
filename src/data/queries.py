"""Reusable SQL queries for the Job Market Intelligence platform.

Every function in this module runs one parameterized statement through
:func:`src.data.database.fetch_dataframe` and returns a ``pandas.DataFrame``.
They are the Python equivalent of the SQL files in ``database/queries/``,
written so a future dashboard can simply call, for example,
``get_top_skills(limit=5)`` and receive a DataFrame to plot.

Two rules apply everywhere in this file:

1. **Parameterised SQL only.** Values that come from a caller (``limit``,
   a company name, an industry) are always passed as psycopg placeholders
   (``%s``). They are never pasted into the SQL text, which makes SQL
   injection impossible.
2. **Never mix currencies or pay periods.** A salary is only comparable to
   another salary with the same ``currency`` and ``salary_period``, so
   :func:`get_average_salary_by_role` groups by both - matching the
   reasoning in ``database/queries/02_salary_analysis.sql``.

Usage::

    from src.data.queries import get_all_jobs, get_top_skills

    jobs = get_all_jobs()          # 40 rows
    skills = get_top_skills(limit=5)
"""

from __future__ import annotations

from typing import Sequence

import pandas as pd

from src.data.database import fetch_dataframe

#: Upper bound for any ``limit`` argument. It stops a mistyped ``limit=100000``
#: from pulling the whole table into memory during a dashboard refresh.
MAX_LIMIT: int = 1000

#: Seniority bands, shared by get_experience_distribution().
#: The order here is the reporting order; the gaps make the values sort
#: correctly while staying readable.
SENIORITY_BANDS: tuple[str, ...] = (
    "ENTRY (0 years)",
    "JUNIOR (1-2 years)",
    "MID (3-5 years)",
    "SENIOR (6-8 years)",
    "STAFF / PRINCIPAL (9+ years)",
    "NOT SPECIFIED",
)

#: CASE expression turning jobs.experience_min into a seniority band.
#: Undisclosed experience gets its own band so it can never inflate the
#: junior share of the market.
_EXPERIENCE_BAND_CASE = """
    CASE
        WHEN j.experience_min IS NULL THEN 'NOT SPECIFIED'
        WHEN j.experience_min = 0      THEN 'ENTRY (0 years)'
        WHEN j.experience_min <= 2     THEN 'JUNIOR (1-2 years)'
        WHEN j.experience_min <= 5     THEN 'MID (3-5 years)'
        WHEN j.experience_min <= 8     THEN 'SENIOR (6-8 years)'
        ELSE 'STAFF / PRINCIPAL (9+ years)'
    END
"""


def _validate_limit(limit: int, name: str = "limit") -> int:
    """Return ``limit`` if it is a sane positive integer, else raise ValueError."""
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError(f"{name} must be an int, got {type(limit).__name__}.")
    if limit < 1:
        raise ValueError(f"{name} must be 1 or greater, got {limit}.")
    if limit > MAX_LIMIT:
        raise ValueError(f"{name} must be {MAX_LIMIT} or less, got {limit}.")
    return limit


def _as_float(frame: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """Convert PostgreSQL ``NUMERIC`` columns to float for charting.

    psycopg returns ``NUMERIC`` as ``decimal.Decimal``, which pandas can only
    store as ``object``. Charts and averages need real numbers, so the salary
    columns are converted here once instead of in every future call site.
    """
    for column in columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def get_all_jobs() -> pd.DataFrame:
    """Return every job posting, newest first, with its company details.

    Columns: ``job_id``, ``company_id``, ``company_name``, ``industry``,
    ``job_title``, ``location``, ``country``, ``employment_type``,
    ``work_mode``, ``experience_min``, ``experience_max``, ``salary_min``,
    ``salary_max``, ``currency``, ``salary_period``, ``posted_date``.

    The long ``description`` column is deliberately left out so the DataFrame
    stays light enough for a dashboard; select it explicitly if it is needed.
    """
    frame = fetch_dataframe(
        """
        SELECT
            j.job_id,
            c.company_id,
            c.company_name,
            c.industry,
            j.job_title,
            j.location,
            j.country,
            j.employment_type,
            j.work_mode,
            j.experience_min,
            j.experience_max,
            j.salary_min,
            j.salary_max,
            j.currency,
            j.salary_period,
            j.posted_date
        FROM jobs j
        JOIN companies c
            ON c.company_id = j.company_id
        ORDER BY j.posted_date DESC, j.job_id
        """
    )
    return _as_float(frame, ("salary_min", "salary_max"))


def get_job_counts_by_role() -> pd.DataFrame:
    """Return the number of postings per job title (the "role").

    Columns: ``role``, ``job_count``, ``company_count``, ``pct_of_all_jobs``.
    Ordered by ``job_count`` descending.
    """
    return fetch_dataframe(
        """
        SELECT
            j.job_title                                        AS role,
            COUNT(*)                                           AS job_count,
            COUNT(DISTINCT j.company_id)                       AS company_count,
            ROUND(
                100.0 * COUNT(*) / NULLIF((SELECT COUNT(*) FROM jobs), 0),
                2
            )                                                  AS pct_of_all_jobs
        FROM jobs j
        GROUP BY j.job_title
        ORDER BY job_count DESC, role
        """
    )


def get_job_counts_by_country() -> pd.DataFrame:
    """Return the number of postings per country.

    Columns: ``country``, ``job_count``, ``company_count``,
    ``pct_of_all_jobs``, ``earliest_posted_date``, ``latest_posted_date``.
    Ordered by ``job_count`` descending.
    """
    return fetch_dataframe(
        """
        SELECT
            j.country                                          AS country,
            COUNT(*)                                           AS job_count,
            COUNT(DISTINCT j.company_id)                       AS company_count,
            ROUND(
                100.0 * COUNT(*) / NULLIF((SELECT COUNT(*) FROM jobs), 0),
                2
            )                                                  AS pct_of_all_jobs,
            MIN(j.posted_date)                                 AS earliest_posted_date,
            MAX(j.posted_date)                                 AS latest_posted_date
        FROM jobs j
        GROUP BY j.country
        ORDER BY job_count DESC, country
        """
    )


def get_job_counts_by_work_mode() -> pd.DataFrame:
    """Return the number of postings per work arrangement (REMOTE/HYBRID/...).

    Columns: ``work_mode``, ``job_count``, ``company_count``,
    ``pct_of_all_jobs``. Ordered by ``job_count`` descending.
    """
    return fetch_dataframe(
        """
        SELECT
            j.work_mode                                        AS work_mode,
            COUNT(*)                                           AS job_count,
            COUNT(DISTINCT j.company_id)                       AS company_count,
            ROUND(
                100.0 * COUNT(*) / NULLIF((SELECT COUNT(*) FROM jobs), 0),
                2
            )                                                  AS pct_of_all_jobs
        FROM jobs j
        GROUP BY j.work_mode
        ORDER BY job_count DESC, work_mode
        """
    )


def get_top_skills(limit: int = 10) -> pd.DataFrame:
    """Return the most requested skills across all postings.

    :param limit: how many skills to return (1 to ``MAX_LIMIT``).
    :returns: ``skill_id``, ``skill_name``, ``skill_category``,
        ``job_count``, ``company_count``, ``pct_of_all_jobs``, ordered by
        ``job_count`` descending.
    :raises TypeError: if ``limit`` is not an int.
    :raises ValueError: if ``limit`` is below 1 or above ``MAX_LIMIT``.

    Skills with no demand at all are excluded - they are not "top" anything.
    """
    limit = _validate_limit(limit)

    return fetch_dataframe(
        """
        SELECT
            s.skill_id,
            s.skill_name,
            s.skill_category,
            COUNT(DISTINCT js.job_id)                         AS job_count,
            COUNT(DISTINCT j.company_id)                      AS company_count,
            ROUND(
                100.0 * COUNT(DISTINCT js.job_id)
                    / NULLIF((SELECT COUNT(*) FROM jobs), 0),
                2
            )                                                  AS pct_of_all_jobs
        FROM skills s
        JOIN job_skills js
            ON js.skill_id = s.skill_id
        JOIN jobs j
            ON j.job_id = js.job_id
        GROUP BY s.skill_id, s.skill_name, s.skill_category
        ORDER BY job_count DESC, s.skill_name
        LIMIT %s
        """,
        (limit,),
    )


def get_jobs_by_company(company_name: str) -> pd.DataFrame:
    """Return every posting from one company, newest first.

    :param company_name: the employer name as stored in
        ``companies.company_name``. The match is case-insensitive, so
        "novabyte technologies" and "Novabyte Technologies" both work.
    :returns: the same columns as :func:`get_all_jobs`, or an empty DataFrame
        with those columns if the company is not in the database.
    :raises TypeError: if ``company_name`` is not a string.
    :raises ValueError: if ``company_name`` is blank.

    ``WHERE lower(c.company_name) = lower(%s)`` is still fully parameterised:
    the name travels as a bound value, never as SQL text.
    """
    if not isinstance(company_name, str):
        raise TypeError(f"company_name must be a str, got {type(company_name).__name__}.")
    if not company_name.strip():
        raise ValueError("company_name must not be blank.")

    frame = fetch_dataframe(
        """
        SELECT
            j.job_id,
            c.company_name,
            c.industry,
            c.headquarters,
            j.job_title,
            j.location,
            j.country,
            j.employment_type,
            j.work_mode,
            j.experience_min,
            j.experience_max,
            j.salary_min,
            j.salary_max,
            j.currency,
            j.salary_period,
            j.posted_date
        FROM jobs j
        JOIN companies c
            ON c.company_id = j.company_id
        WHERE lower(c.company_name) = lower(%s)
        ORDER BY j.posted_date DESC, j.job_id
        """,
        (company_name.strip(),),
    )
    return _as_float(frame, ("salary_min", "salary_max"))


def get_average_salary_by_role() -> pd.DataFrame:
    """Return average advertised salary per role.

    Columns: ``role``, ``currency``, ``salary_period``, ``jobs_with_salary``,
    ``company_count``, ``avg_salary_min``, ``avg_salary_max``,
    ``avg_salary_midpoint``, ``lowest_salary_min``, ``highest_salary_max``.

    Rows are grouped by ``currency`` **and** ``salary_period`` on purpose. The
    database has no exchange-rate table, so averaging INR with USD, or a
    yearly figure with an hourly one, would produce a meaningless number.
    Postings with no disclosed salary are excluded, and ``jobs_with_salary``
    shows how many postings each average is based on.
    """
    frame = fetch_dataframe(
        """
        SELECT
            j.job_title                                        AS role,
            j.currency                                         AS currency,
            j.salary_period                                    AS salary_period,
            COUNT(*)                                           AS jobs_with_salary,
            COUNT(DISTINCT j.company_id)                       AS company_count,
            ROUND(AVG(j.salary_min), 2)                        AS avg_salary_min,
            ROUND(AVG(j.salary_max), 2)                        AS avg_salary_max,
            ROUND(AVG((j.salary_min + j.salary_max) / 2), 2)   AS avg_salary_midpoint,
            MIN(j.salary_min)                                  AS lowest_salary_min,
            MAX(j.salary_max)                                  AS highest_salary_max
        FROM jobs j
        WHERE j.salary_min IS NOT NULL
          AND j.salary_max IS NOT NULL
        GROUP BY j.job_title, j.currency, j.salary_period
        ORDER BY role, currency, salary_period
        """
    )
    return _as_float(
        frame,
        (
            "avg_salary_min",
            "avg_salary_max",
            "avg_salary_midpoint",
            "lowest_salary_min",
            "highest_salary_max",
        ),
    )


def get_jobs_by_industry(industry: str | None = None) -> pd.DataFrame:
    """Return job postings, optionally narrowed to one industry.

    :param industry: an industry name as stored in ``companies.industry``
        (case-insensitive). ``None`` returns postings for every industry.
    :returns: one row per posting with ``industry`` included, newest first.
        An empty DataFrame (same columns) if the industry is unknown.
    :raises TypeError: if ``industry`` is neither ``None`` nor a string.
    :raises ValueError: if ``industry`` is blank.

    Only the two fixed SQL fragments below are chosen between - the value
    itself is always bound as a parameter.
    """
    where_clause = ""
    params: tuple[str, ...] = ()
    if industry is not None:
        if not isinstance(industry, str):
            raise TypeError(
                f"industry must be a str or None, got {type(industry).__name__}."
            )
        if not industry.strip():
            raise ValueError("industry must not be blank; pass None for all industries.")
        where_clause = "WHERE lower(c.industry) = lower(%s)"
        params = (industry.strip(),)

    frame = fetch_dataframe(
        f"""
        SELECT
            j.job_id,
            c.company_name,
            c.industry,
            c.headquarters,
            j.job_title,
            j.location,
            j.country,
            j.employment_type,
            j.work_mode,
            j.experience_min,
            j.experience_max,
            j.salary_min,
            j.salary_max,
            j.currency,
            j.salary_period,
            j.posted_date
        FROM jobs j
        JOIN companies c
            ON c.company_id = j.company_id
        {where_clause}
        ORDER BY c.industry, j.posted_date DESC, j.job_id
        """,
        params or None,
    )
    return _as_float(frame, ("salary_min", "salary_max"))


def get_experience_distribution() -> pd.DataFrame:
    """Return how the market splits across seniority bands.

    Columns: ``seniority_band``, ``jobs_posted``, ``companies_hiring``,
    ``pct_of_all_jobs``, ``avg_experience_midpoint_years``.

    Bands run from ENTRY to STAFF / PRINCIPAL, with NOT SPECIFIED last, so
    the rows read in seniority order rather than by size.
    """
    frame = fetch_dataframe(
        f"""
        SELECT
            {_EXPERIENCE_BAND_CASE.strip()}                  AS seniority_band,
            CASE
                WHEN j.experience_min IS NULL THEN 6
                WHEN j.experience_min = 0      THEN 1
                WHEN j.experience_min <= 2     THEN 2
                WHEN j.experience_min <= 5     THEN 3
                WHEN j.experience_min <= 8     THEN 4
                ELSE 5
            END                                                AS band_order,
            COUNT(*)                                           AS jobs_posted,
            COUNT(DISTINCT c.company_id)                       AS companies_hiring,
            ROUND(
                100.0 * COUNT(*) / NULLIF((SELECT COUNT(*) FROM jobs), 0),
                2
            )                                                  AS pct_of_all_jobs,
            ROUND(AVG((j.experience_min + j.experience_max) / 2.0), 2)
                                                            AS avg_experience_midpoint_years
        FROM jobs j
        JOIN companies c
            ON c.company_id = j.company_id
        GROUP BY
            {_EXPERIENCE_BAND_CASE.strip()},
            CASE
                WHEN j.experience_min IS NULL THEN 6
                WHEN j.experience_min = 0      THEN 1
                WHEN j.experience_min <= 2     THEN 2
                WHEN j.experience_min <= 5     THEN 3
                WHEN j.experience_min <= 8     THEN 4
                ELSE 5
            END
        ORDER BY band_order
        """
    )
    frame = _as_float(frame, ("avg_experience_midpoint_years",))
    # band_order is a helper column for sorting only, not part of the result.
    return frame.drop(columns=["band_order"])


def get_recent_jobs(limit: int = 10) -> pd.DataFrame:
    """Return the most recently posted jobs.

    :param limit: how many rows to return (1 to ``MAX_LIMIT``).
    :returns: the same columns as :func:`get_all_jobs`, ordered by
        ``posted_date`` descending, then ``job_id`` descending so the order is
        stable when several jobs share a date.
    :raises TypeError: if ``limit`` is not an int.
    :raises ValueError: if ``limit`` is below 1 or above ``MAX_LIMIT``.
    """
    limit = _validate_limit(limit)

    return fetch_dataframe(
        """
        SELECT
            j.job_id,
            c.company_name,
            c.industry,
            j.job_title,
            j.location,
            j.country,
            j.employment_type,
            j.work_mode,
            j.experience_min,
            j.experience_max,
            j.salary_min,
            j.salary_max,
            j.currency,
            j.salary_period,
            j.posted_date
        FROM jobs j
        JOIN companies c
            ON c.company_id = j.company_id
        ORDER BY j.posted_date DESC, j.job_id DESC
        LIMIT %s
        """,
        (limit,),
    )


def get_job_skill_links() -> pd.DataFrame:
    """Return the job <-> skill junction table, ready for analysis.

    Columns: ``job_id``, ``skill_id``, ``skill_name``, ``skill_category``.
    One row means "this job requires this skill", so the frame has one row per
    requirement (242 rows for the seed data).

    This is the flattened form of the many-to-many relationship. It exists so
    skill demand can be recounted for an arbitrary subset of jobs - for
    example the postings left after a dashboard filter - without re-querying
    the database for every filter combination.
    """
    return fetch_dataframe(
        """
        SELECT
            js.job_id,
            s.skill_id,
            s.skill_name,
            s.skill_category
        FROM job_skills js
        JOIN skills s
            ON s.skill_id = js.skill_id
        ORDER BY js.job_id, s.skill_name
        """
    )


def get_table_row_counts() -> pd.DataFrame:
    """Return the row count of each core table.

    Columns: ``table_name``, ``row_count`` for ``companies``, ``jobs``,
    ``skills``, ``job_skills``. Useful as a health check after loading data,
    and as a quick "is the database populated?" test.
    """
    return fetch_dataframe(
        """
        SELECT 'companies' AS table_name, COUNT(*) AS row_count FROM companies
        UNION ALL
        SELECT 'jobs' AS table_name, COUNT(*) AS row_count FROM jobs
        UNION ALL
        SELECT 'skills' AS table_name, COUNT(*) AS row_count FROM skills
        UNION ALL
        SELECT 'job_skills' AS table_name, COUNT(*) AS row_count FROM job_skills
        ORDER BY table_name
        """
    )


# =============================================================================
# SKILL GAP ANALYZER - the data source for the Skill Gap Analyzer tab
# =============================================================================
# These three functions answer "what does this role require, and which skills
# exist at all?". The comparison itself is NOT done in SQL: it is a transparent
# rule-based calculation in ``dashboard.components.analyze_skill_gap``, so the
# number on screen can be explained without running a query.


def get_available_job_roles() -> pd.DataFrame:
    """Return every advertised job title, with how many skills it requires.

    Columns: ``role``, ``job_count``, ``company_count``, ``skill_count``.

    This is what populates the Skill Gap Analyzer's target-role dropdown, so
    the list of selectable roles comes from ``jobs`` and is never hardcoded. A
    role with no skill requirements still appears, with ``skill_count`` of 0, so
    the tab can explain that instead of silently hiding it.

    The ``LEFT JOIN`` keeps those skill-less roles in the list, and
    ``COUNT(DISTINCT j.job_id)`` is what stops the join from inflating the
    posting count - a plain ``COUNT(*)`` would count one job once per skill it
    requires.
    """
    return fetch_dataframe(
        """
        SELECT
            j.job_title                                        AS role,
            COUNT(DISTINCT j.job_id)                           AS job_count,
            COUNT(DISTINCT j.company_id)                       AS company_count,
            COUNT(DISTINCT js.skill_id)                        AS skill_count
        FROM jobs j
        LEFT JOIN job_skills js
            ON js.job_id = j.job_id
        GROUP BY j.job_title
        ORDER BY job_count DESC, role
        """
    )


def get_required_skills_for_role(role: str) -> pd.DataFrame:
    """Return the skills required by the postings advertised under ``role``.

    :param role: a job title as stored in ``jobs.job_title``. The match is
        case-insensitive and whitespace-trimmed on both sides, so
        "machine learning engineer" finds "Machine Learning Engineer".
    :returns: ``skill_id``, ``skill_name``, ``skill_category``, ``job_count``,
        ``company_count``, ``pct_of_role_jobs`` - one row per DISTINCT skill,
        most widely required first, then alphabetically.
    :raises TypeError: if ``role`` is not a string.
    :raises ValueError: if ``role`` is blank.

    ``job_count`` is how many of the role's postings list the skill, and
    ``pct_of_role_jobs`` expresses that as a share of the role's postings that
    declare any skill requirement at all. Because the two postings of a role
    overlap, the percentages do not add up to 100 - that is intended, and it is
    what makes "required by every posting" visible at the top of the list.

    ``WHERE lower(btrim(j.job_title)) = lower(btrim(%s))`` is still fully
    parameterised: the role travels as a bound value, never as SQL text, so a
    title like ``'; DROP TABLE jobs; --`` simply matches nothing. It is also
    exactly the comparison the ``idx_jobs_job_title_lower`` index supports.
    """
    if not isinstance(role, str):
        raise TypeError(f"role must be a str, got {type(role).__name__}.")
    if not role.strip():
        raise ValueError("role must not be blank.")

    return fetch_dataframe(
        """
        SELECT
            s.skill_id,
            s.skill_name,
            s.skill_category,
            COUNT(DISTINCT js.job_id)                         AS job_count,
            COUNT(DISTINCT j.company_id)                       AS company_count,
            ROUND(
                100.0 * COUNT(DISTINCT js.job_id)
                    / NULLIF(COUNT(DISTINCT j.job_id), 0),
                2
            )                                                  AS pct_of_role_jobs
        FROM jobs j
        JOIN job_skills js
            ON js.job_id = j.job_id
        JOIN skills s
            ON s.skill_id = js.skill_id
        WHERE lower(btrim(j.job_title)) = lower(btrim(%s))
        GROUP BY s.skill_id, s.skill_name, s.skill_category
        ORDER BY job_count DESC, s.skill_name
        """,
        (role.strip(),),
    )


def get_skill_catalog() -> pd.DataFrame:
    """Return every skill the database knows about, alphabetically.

    Columns: ``skill_id``, ``skill_name``, ``skill_category``.

    The Skill Gap Analyzer needs this to tell two very different cases apart:
    a skill the market does not know at all (a typo or a name this database has
    never seen) versus a real skill that simply is not required for the chosen
    role. Only the second one can ever contribute to the match percentage.
    """
    return fetch_dataframe(
        """
        SELECT
            s.skill_id,
            s.skill_name,
            s.skill_category
        FROM skills s
        ORDER BY s.skill_name
        """
    )


# =============================================================================
# COMPANIES - the employer reference table, with how active each one is
# =============================================================================


def get_all_companies() -> pd.DataFrame:
    """Return every employer, alphabetically, with how many postings each.

    Columns: ``company_id``, ``company_name``, ``industry``,
    ``company_size``, ``headquarters``, ``job_count``.

    A company with no postings still appears, with ``job_count`` of 0,
    because the ``LEFT JOIN`` keeps employers that are not currently hiring
    visible next to the ones that are.
    """
    return fetch_dataframe(
        """
        SELECT
            c.company_id,
            c.company_name,
            c.industry,
            c.company_size,
            c.headquarters,
            COUNT(DISTINCT j.job_id)                AS job_count
        FROM companies c
        LEFT JOIN jobs j
            ON j.company_id = c.company_id
        GROUP BY c.company_id
        ORDER BY c.company_name
        """
    )
