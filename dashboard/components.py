"""Reusable building blocks for the Streamlit dashboard.

This module holds two kinds of function:

* **Pure helpers** - ``apply_filters``, ``kpi_cards``, ``build_skill_demand``,
  ``build_skills_by_category``, ``experience_distribution``, ``salary_units``,
  ``build_recent_jobs`` and friends. Plain pandas, no Streamlit calls, so the
  dashboard's logic can be tested without starting a server.
* **Renderers** - ``render_header``, ``render_sidebar``, ``render_kpis``,
  ``render_recent_jobs`` and the ``chart_*`` functions. These are the
  Streamlit and Plotly layer.

No database code belongs here. Every figure starts from a DataFrame that
``src.data.queries`` already produced, and no connection is ever opened or
cached here.

Two rules are enforced by the code rather than by convention:

1. **No KPI, chart or table value is hardcoded.** Everything is counted from
   the DataFrames that came out of PostgreSQL.
2. **Currencies and pay periods are never mixed.** Salary charts are built
   from a single ``(currency, salary_period)`` pair at a time, and the
   cross-currency view counts postings instead of summing amounts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.graph_objects import Figure

from dashboard.styles import (
    ACCENT,
    BORDER,
    FONT_FAMILY,
    PLOTLY_CONFIG,
    SEQUENTIAL,
    SUCCESS,
    TEXT_MUTED,
    WARNING,
    WORK_MODE_COLORS,
    apply_figure_theme,
)
from ml.preprocessing import SKILL_SEPARATOR_PATTERN
from ml.preprocessing import normalize_skill_name as _normalize_skill_name
from ml.preprocessing import parse_skill_list
from src.data.queries import SENIORITY_BANDS

# =============================================================================
# CONFIGURATION
# =============================================================================

#: Sidebar filter definitions, in display order. The value is the column in the
#: DataFrame returned by ``get_all_jobs()``; the key is the widget state key.
FILTERS: tuple[tuple[str, str, str], ...] = (
    ("country", "Country", "filter_country"),
    ("work_mode", "Work Mode", "filter_work_mode"),
    ("employment_type", "Employment Type", "filter_employment_type"),
    ("industry", "Industry", "filter_industry"),
    ("job_title", "Job Role", "filter_role"),
)

#: Only these two columns are stored as UPPER_SNAKE_CASE codes, so only these
#: two are prettified for display ("FULL_TIME" -> "Full Time"). Job titles and
#: industries are already human-readable and must not be title-cased, or
#: "AI Engineer" would become "Ai Engineer".
CODE_COLUMNS: frozenset[str] = frozenset({"work_mode", "employment_type"})

FILTER_KEYS: tuple[str, ...] = tuple(key for _, _, key in FILTERS)

#: Seniority bands, imported from the data layer so this file and the SQL in
#: database/queries/05_advanced_analysis.sql can never drift apart.
EXPERIENCE_BAND_ORDER: list[str] = list(SENIORITY_BANDS)

#: Latest postings shown by default in the Recent Jobs tab.
RECENT_JOBS_LIMIT: int = 200

#: Columns of the Recent Jobs table, in order, mapped from get_all_jobs().
RECENT_JOB_COLUMNS: dict[str, str] = {
    "job_title": "Job Title",
    "company_name": "Company",
    "industry": "Industry",
    "location": "Location",
    "country": "Country",
    "work_mode": "Work Mode",
    "employment_type": "Employment Type",
    "experience": "Experience",
    "salary": "Salary",
    "currency": "Currency",
    "salary_period": "Salary Period",
    "posted_date": "Posted Date",
}

#: Redacts anything that looks like a credential, as a last line of defence
#: before a driver message is rendered in the browser. The key may carry a
#: prefix ("DB_PASSWORD", "postgres_pwd") and any separator, because that is
#: exactly how the project's own .env file spells these settings.
_SECRET_PATTERN = re.compile(
    r"(?i)\b([\w.-]*(?:password|passwd|pwd|secret|token)[\w.-]*)\s*[=:]\s*\S+"
)

# -----------------------------------------------------------------------------
# SKILL GAP ANALYZER - the rule set, stated in one place
# -----------------------------------------------------------------------------
# Skill normalization lives in ``ml.preprocessing`` and is re-exported here,
# not reimplemented. The rule-based Skill Gap Analyzer and the TF-IDF role
# recommender must compare names under identical rules, or the side-by-side
# comparison the dashboard draws would be comparing two different questions.
# ``/`` and "+" are deliberately NOT separators, because real skill names
# contain them ("CI/CD", "C++").
#: Characters treated as separators in the user's free-text skill list. A comma
#: is the documented format; newline, semicolon and pipe are accepted too, so a
#: list pasted from a resume or a notes app still parses.
SKILL_SEPARATOR_PATTERN = SKILL_SEPARATOR_PATTERN

#: Canonical column set of every skill frame the analyzer passes around. All
#: three result frames (required / matched / missing) share it, so a single
#: table renderer handles any of them.
SKILL_GAP_COLUMNS: tuple[str, ...] = (
    "skill_name",
    "skill_category",
    "job_count",
    "pct_of_role_jobs",
)

#: Shown instead of a blank category so a table cell is never empty.
UNCATEGORISED: str = "Uncategorised"


def redact(text: object) -> str:
    """Return ``text`` with anything credential-shaped replaced by ``***``."""
    return _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=***", str(text))


# =============================================================================
# PURE HELPERS - the dashboard logic, no Streamlit
# =============================================================================


def format_filter_value(column: str, value: Any) -> str:
    """Render a stored filter value for display in the sidebar."""
    text = str(value)
    if column in CODE_COLUMNS:
        return text.replace("_", " ").title()
    return text


def apply_filters(jobs: pd.DataFrame, selections: dict[str, Iterable[Any]]) -> pd.DataFrame:
    """Return the rows of ``jobs`` that match every active filter.

    An empty selection means "no filter for this column", so the default view
    is the whole market. Matching uses ``isin`` on the values the sidebar
    produced, so no filter value is ever concatenated into SQL.
    """
    filtered = jobs
    for column, values in selections.items():
        chosen = [value for value in (values or []) if value is not None]
        if chosen:
            filtered = filtered[filtered[column].isin(chosen)]
    return filtered.reset_index(drop=True)


def _pct(part: float, whole: float) -> str:
    """Format ``part`` as a percentage of ``whole`` for a KPI caption."""
    if not whole:
        return "0% of selection"
    return f"{100.0 * part / whole:.1f}% of selection"


def kpi_cards(
    jobs: pd.DataFrame,
    links: pd.DataFrame,
    market_job_count: int,
) -> list[dict[str, str]]:
    """Build the six KPI cards from the filtered selection.

    Every number is counted from the DataFrames. ``market_job_count`` (the
    unfiltered total from ``get_table_row_counts``) is only used for the
    "of N in the market" caption, never for the value itself.
    """
    total_jobs = int(len(jobs))
    companies = int(jobs["company_id"].nunique()) if not jobs.empty else 0
    skills = int(links["skill_id"].nunique()) if not links.empty else 0

    def work_mode_count(mode: str) -> int:
        if jobs.empty:
            return 0
        return int((jobs["work_mode"] == mode).sum())

    return [
        {
            "label": "Total Jobs",
            "value": f"{total_jobs:,}",
            "sub": f"of {market_job_count:,} in the market",
            "accent": ACCENT,
        },
        {
            "label": "Companies Hiring",
            "value": f"{companies:,}",
            "sub": "employers with open roles",
            "accent": ACCENT,
        },
        {
            "label": "Total Skills",
            "value": f"{skills:,}",
            "sub": "distinct skills demanded",
            "accent": ACCENT,
        },
        {
            "label": "Remote Jobs",
            "value": f"{work_mode_count('REMOTE'):,}",
            "sub": _pct(work_mode_count("REMOTE"), total_jobs),
            "accent": WORK_MODE_COLORS["REMOTE"],
        },
        {
            "label": "Hybrid Jobs",
            "value": f"{work_mode_count('HYBRID'):,}",
            "sub": _pct(work_mode_count("HYBRID"), total_jobs),
            "accent": WORK_MODE_COLORS["HYBRID"],
        },
        {
            "label": "Onsite Jobs",
            "value": f"{work_mode_count('ONSITE'):,}",
            "sub": _pct(work_mode_count("ONSITE"), total_jobs),
            "accent": WORK_MODE_COLORS["ONSITE"],
        },
    ]


def build_skill_demand(links: pd.DataFrame, jobs: pd.DataFrame) -> pd.DataFrame:
    """Count skill demand for the jobs left after filtering.

    :param links: ``get_job_skill_links()`` output (job_id, skill_id, ...).
    :param jobs: the filtered postings.
    :returns: ``skill_name``, ``skill_category``, ``job_count``,
        ``company_count``, ``pct_of_jobs``, most demanded first.

    The percentage is "share of the selected jobs that require this skill", so
    a skill wanted by every posting reads 100%.
    """
    empty = pd.DataFrame(
        columns=["skill_name", "skill_category", "job_count", "company_count", "pct_of_jobs"]
    )
    if links.empty or jobs.empty:
        return empty

    subset = links[links["job_id"].isin(set(jobs["job_id"]))]
    if subset.empty:
        return empty

    merged = subset.merge(jobs[["job_id", "company_id"]], on="job_id", how="left")
    demand = (
        merged.groupby(["skill_name", "skill_category"], as_index=False)
        .agg(
            job_count=("job_id", "nunique"),
            company_count=("company_id", "nunique"),
        )
    )
    total_jobs = int(jobs["job_id"].nunique())
    demand["pct_of_jobs"] = (
        (100.0 * demand["job_count"] / total_jobs).round(2) if total_jobs else 0.0
    )
    return demand.sort_values(
        ["job_count", "skill_name"], ascending=[False, True]
    ).reset_index(drop=True)


def build_skills_by_category(demand: pd.DataFrame) -> pd.DataFrame:
    """Roll the skill demand up to one row per skill category.

    :returns: ``skill_category``, ``skill_count``, ``job_requirements``,
        ``pct_of_demand``, largest share first.
    """
    empty = pd.DataFrame(
        columns=["skill_category", "skill_count", "job_requirements", "pct_of_demand"]
    )
    if demand.empty:
        return empty

    by_category = (
        demand.groupby("skill_category", as_index=False)
        .agg(
            skill_count=("skill_name", "nunique"),
            job_requirements=("job_count", "sum"),
        )
    )
    total_requirements = int(by_category["job_requirements"].sum())
    by_category["pct_of_demand"] = (
        (100.0 * by_category["job_requirements"] / total_requirements).round(2)
        if total_requirements
        else 0.0
    )
    return by_category.sort_values("job_requirements", ascending=False).reset_index(drop=True)


def experience_band(experience_min: Any) -> str:
    """Map ``jobs.experience_min`` to a seniority band.

    Mirrors the CASE expression in
    ``database/queries/05_advanced_analysis.sql`` (query 13) and the band names
    come from ``src.data.queries.SENIORITY_BANDS``, so the pandas version and
    the SQL version cannot disagree on either the thresholds or the wording.
    Undisclosed experience gets its own band rather than being folded into
    entry level, which would otherwise overstate the junior share.
    """
    if experience_min is None or pd.isna(experience_min):
        return "NOT SPECIFIED"
    years = float(experience_min)
    if years == 0:
        return "ENTRY (0 years)"
    if years <= 2:
        return "JUNIOR (1-2 years)"
    if years <= 5:
        return "MID (3-5 years)"
    if years <= 8:
        return "SENIOR (6-8 years)"
    return "STAFF / PRINCIPAL (9+ years)"


def experience_distribution(jobs: pd.DataFrame) -> pd.DataFrame:
    """Summarise the filtered postings by seniority band.

    :returns: ``seniority_band``, ``jobs_posted``, ``companies_hiring``,
        ``pct_of_all_jobs``, ``avg_experience_midpoint_years``. Every band is
        present, even when it has no postings, so the chart keeps a stable
        shape as filters change.
    """
    columns = [
        "seniority_band",
        "jobs_posted",
        "companies_hiring",
        "pct_of_all_jobs",
        "avg_experience_midpoint_years",
    ]
    if jobs.empty:
        return pd.DataFrame(
            {
                "seniority_band": EXPERIENCE_BAND_ORDER,
                "jobs_posted": 0,
                "companies_hiring": 0,
                "pct_of_all_jobs": 0.0,
                "avg_experience_midpoint_years": pd.NA,
            }
        )[columns]

    frame = jobs.copy()
    frame["midpoint"] = (frame["experience_min"] + frame["experience_max"]) / 2.0
    frame["seniority_band"] = [experience_band(value) for value in frame["experience_min"]]

    distribution = (
        frame.groupby("seniority_band", as_index=False)
        .agg(
            jobs_posted=("job_id", "nunique"),
            companies_hiring=("company_id", "nunique"),
            avg_experience_midpoint_years=("midpoint", "mean"),
        )
    )
    total_jobs = int(len(frame))
    distribution["pct_of_all_jobs"] = (
        (100.0 * distribution["jobs_posted"] / total_jobs).round(2) if total_jobs else 0.0
    )
    distribution["avg_experience_midpoint_years"] = distribution[
        "avg_experience_midpoint_years"
    ].round(2)

    # Reindex onto the canonical band order and fill the gaps with zeroes.
    distribution = (
        distribution.set_index("seniority_band")
        .reindex(EXPERIENCE_BAND_ORDER)
        .fillna({"jobs_posted": 0, "companies_hiring": 0, "pct_of_all_jobs": 0.0})
        .reset_index()
    )
    # Filling the empty bands upcasts the counts to float; put them back to
    # whole numbers so the table and the KPI-style formatting stay tidy.
    distribution["jobs_posted"] = distribution["jobs_posted"].astype(int)
    distribution["companies_hiring"] = distribution["companies_hiring"].astype(int)
    return distribution[columns]


def salary_units(jobs: pd.DataFrame) -> list[tuple[str, str]]:
    """Return the ``(currency, salary_period)`` pairs present in ``jobs``.

    A salary is only comparable to another salary with the same currency and
    the same pay period, so the dashboard treats each pair as its own unit and
    never adds them together.
    """
    if jobs.empty:
        return []
    disclosed = jobs[jobs["salary_min"].notna() & jobs["salary_max"].notna()]
    if disclosed.empty:
        return []
    pairs = disclosed[["currency", "salary_period"]].dropna().drop_duplicates()
    return sorted((str(currency), str(period)) for currency, period in pairs.itertuples(index=False))


def unit_label(unit: tuple[str, str]) -> str:
    """Human-readable name of a salary unit, e.g. ``INR · YEARLY``."""
    currency, period = unit
    return f"{currency} · {period}"


def salary_midpoints(jobs: pd.DataFrame) -> pd.Series:
    """Midpoint of each advertised salary range, or NaN where not disclosed.

    Used by the Recent Jobs table so a range can be compared inside a single
    salary unit; never summed across currencies or pay periods.
    """
    midpoint = (jobs["salary_min"] + jobs["salary_max"]) / 2.0
    return midpoint.where(jobs["currency"].notna() & jobs["salary_period"].notna())


#: Column order of the filtered salary aggregate, identical to the DataFrame
#: returned by ``queries.get_average_salary_by_role()`` so the same charts and
#: the same table renderer accept either one.
SALARY_BY_ROLE_COLUMNS: tuple[str, ...] = (
    "role",
    "currency",
    "salary_period",
    "jobs_with_salary",
    "company_count",
    "avg_salary_min",
    "avg_salary_max",
    "avg_salary_midpoint",
    "lowest_salary_min",
    "highest_salary_max",
)


def build_salary_by_role(jobs: pd.DataFrame) -> pd.DataFrame:
    """Recompute the per-role salary aggregate for a filtered job selection.

    This mirrors ``queries.get_average_salary_by_role()`` column for column -
    same grouping, same exclusions, same rounding - but over an already-loaded
    DataFrame instead of a fresh query. Without it, narrowing the sidebar would
    still plot roles that have no posting in the selection, which reads as if
    those salaries apply to the filtered result.

    Grouping stays on ``(currency, salary_period)`` for the same reason as the
    SQL: there is no exchange-rate table, so averaging INR with USD, or a
    yearly figure with an hourly one, would be meaningless.
    """
    empty = pd.DataFrame(columns=list(SALARY_BY_ROLE_COLUMNS))
    if jobs.empty:
        return empty

    disclosed = jobs[
        jobs["salary_min"].notna()
        & jobs["salary_max"].notna()
        & jobs["currency"].notna()
        & jobs["salary_period"].notna()
    ]
    if disclosed.empty:
        return empty

    grouped = disclosed.groupby(["job_title", "currency", "salary_period"], sort=True)
    summary = grouped.agg(
        jobs_with_salary=("job_title", "size"),
        company_count=("company_id", "nunique"),
        avg_salary_min=("salary_min", "mean"),
        avg_salary_max=("salary_max", "mean"),
        lowest_salary_min=("salary_min", "min"),
        highest_salary_max=("salary_max", "max"),
    ).reset_index()
    summary["avg_salary_midpoint"] = (summary["avg_salary_min"] + summary["avg_salary_max"]) / 2.0

    summary = summary.rename(columns={"job_title": "role"})
    summary["currency"] = summary["currency"].astype(str)
    summary["salary_period"] = summary["salary_period"].astype(str)
    summary["role"] = summary["role"].astype(str)

    for column in (
        "avg_salary_min",
        "avg_salary_max",
        "avg_salary_midpoint",
        "lowest_salary_min",
        "highest_salary_max",
    ):
        summary[column] = summary[column].round(2)
    for column in ("jobs_with_salary", "company_count"):
        summary[column] = summary[column].astype(int)

    return summary[list(SALARY_BY_ROLE_COLUMNS)].sort_values(
        ["role", "currency", "salary_period"]
    ).reset_index(drop=True)


def build_recent_jobs(jobs: pd.DataFrame) -> pd.DataFrame:
    """Build the recruiter-facing postings table, newest first.

    Salary is shown as one formatted range while currency and pay period stay
    in their own columns, so no reader can mistake a daily rate for a yearly
    salary. Postings without a disclosed salary say so instead of showing 0.
    """
    frame = jobs.copy()
    # Show the stored codes the way a recruiter reads them ("Full Time",
    # "Onsite") while every other column keeps its stored value.
    frame["work_mode"] = [format_filter_value("work_mode", value) for value in frame["work_mode"]]
    frame["employment_type"] = [
        format_filter_value("employment_type", value) for value in frame["employment_type"]
    ]
    frame["experience"] = [
        experience_text(low, high) for low, high in zip(frame["experience_min"], frame["experience_max"])
    ]
    frame["salary"] = [
        format_salary_text(low, high) for low, high in zip(frame["salary_min"], frame["salary_max"])
    ]
    frame["posted_date"] = pd.to_datetime(frame["posted_date"])
    frame = frame.sort_values(["posted_date", "job_id"], ascending=[False, False])
    return frame[list(RECENT_JOB_COLUMNS)].rename(columns=RECENT_JOB_COLUMNS).reset_index(drop=True)


def format_salary_text(salary_min: Any, salary_max: Any) -> str:
    """Format one salary range, or ``Not disclosed`` when there is none."""
    if pd.isna(salary_min) and pd.isna(salary_max):
        return "Not disclosed"
    if pd.isna(salary_min) or pd.isna(salary_max):
        disclosed = salary_min if not pd.isna(salary_min) else salary_max
        return f"From {disclosed:,.0f}"
    return f"{salary_min:,.0f} – {salary_max:,.0f}"


def experience_text(experience_min: Any, experience_max: Any) -> str:
    """Format an experience requirement, e.g. ``3 – 6 yrs``."""
    if pd.isna(experience_min):
        return "Not specified"
    if pd.isna(experience_max):
        return f"{int(experience_min)}+ yrs"
    return f"{int(experience_min)} – {int(experience_max)} yrs"


def top_values(frame: pd.DataFrame, column: str, top: int | None = None) -> pd.DataFrame:
    """Count non-null values of ``column``, most frequent first."""
    counts = (
        frame[column]
        .dropna()
        .value_counts()
        .rename_axis(column)
        .reset_index(name="job_count")
    )
    counts = counts.sort_values(["job_count", column], ascending=[False, True])
    return counts.head(top) if top else counts


def monthly_postings(jobs: pd.DataFrame) -> pd.DataFrame:
    """Count postings per calendar month, oldest first (for trend charts)."""
    if jobs.empty:
        return pd.DataFrame(columns=["month", "job_count"])
    months = (
        pd.to_datetime(jobs["posted_date"])
        .dt.to_period("M")
        .dt.to_timestamp()
    )
    frame = pd.DataFrame({"month": months, "job_id": jobs["job_id"]})
    counts = (
        frame.groupby("month", as_index=False)
        .agg(job_count=("job_id", "nunique"))
        .sort_values("month")
    )
    return counts.reset_index(drop=True)


# =============================================================================
# PURE HELPERS - SKILL GAP ANALYZER
# =============================================================================
# The whole feature is a transparent, rule-based set comparison. There is no
# model, no embedding, no fuzzy match and no synonym table: a skill counts as a
# match if and only if its name, once trimmed, lower-cased and whitespace-
# collapsed, is identical to the name the database stores. "PyTorch" therefore
# never satisfies a "TensorFlow" requirement, which is the correct and
# explainable behaviour for a gap analysis.
#
#     Skill Match %  =  matched required skills
#                       -------------------------  x 100
#                        total required skills
#
# Only skills the role actually requires are in the denominator. A skill the
# user has that the role does not ask for is reported separately and can never
# inflate the score.


def normalize_skill_name(value: str) -> str:
    """Return the comparison form of one skill name.

    Re-exported from :func:`ml.preprocessing.normalize_skill_name` so there is
    exactly one definition of "the same skill" in the project. It trims the
    ends, collapses runs of internal whitespace to a single space and lower-cases,
    so ``"  PyTorch "`` and ``"pytorch"`` are one skill.

    :raises TypeError: if ``value`` is not a string.
    """
    return _normalize_skill_name(value)


def parse_user_skills(raw: str) -> list[str]:
    """Turn the user's free-text skill list into a clean list of skill names.

    "Python, SQL,  python ,Git" becomes ``["Python", "SQL", "Git"]``.

    Implemented by :func:`ml.preprocessing.parse_skill_list` and kept under its
    dashboard name; see :func:`normalize_skill_name` for why the normalization
    rules are shared with the recommender rather than duplicated.

    :raises TypeError: if ``raw`` is neither a string nor ``None``.
    """
    return parse_skill_list(raw)


def format_match_percentage(value: float) -> str:
    """Format a percentage for display, dropping a redundant ``.0``.

    ``60.0`` becomes ``"60%"`` and ``33.333`` becomes ``"33.3%"``. A whole
    number is never shown as ``"60.0%"`` because the Skill Gap tab states
    plain figures such as "0% skill match".
    """
    text = f"{float(value):.1f}"
    if text.endswith(".0"):
        text = text[:-2]
    return f"{text}%"


def _empty_skill_frame() -> pd.DataFrame:
    """An empty frame with exactly the skill-gap columns."""
    return pd.DataFrame(
        {
            "skill_name": pd.Series(dtype="object"),
            "skill_category": pd.Series(dtype="object"),
            "job_count": pd.Series(dtype="int64"),
            "pct_of_role_jobs": pd.Series(dtype="float64"),
        }
    )


def _coerce_skill_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    """Return ``frame`` with the canonical skill-gap columns, in canonical order.

    Only ``skill_name`` is really needed. The other three are filled with
    sensible defaults when absent, so the analyser accepts the leanest possible
    input (a single ``skill_name`` column) without every caller having to
    invent the rest. Rows with a blank skill name are dropped, because a blank
    name could never be matched.
    """
    if frame is None or len(frame) == 0:
        return _empty_skill_frame()

    prepared = frame.copy()
    if "skill_name" not in prepared.columns:
        raise ValueError("a skill frame must have a 'skill_name' column.")

    prepared["skill_name"] = prepared["skill_name"].map(
        lambda value: " ".join(str(value).split())
    )
    prepared = prepared[prepared["skill_name"] != ""]

    if "skill_category" not in prepared.columns:
        prepared["skill_category"] = ""
    prepared["skill_category"] = prepared["skill_category"].fillna("").astype(str)
    prepared.loc[prepared["skill_category"] == "", "skill_category"] = UNCATEGORISED

    if "job_count" not in prepared.columns:
        prepared["job_count"] = 0
    prepared["job_count"] = pd.to_numeric(prepared["job_count"], errors="coerce").fillna(0).astype(int)

    if "pct_of_role_jobs" not in prepared.columns:
        prepared["pct_of_role_jobs"] = 0.0
    prepared["pct_of_role_jobs"] = (
        pd.to_numeric(prepared["pct_of_role_jobs"], errors="coerce").fillna(0.0).astype(float)
    )

    # A skill required by two rows would otherwise be counted twice in the
    # denominator, so keep the first (most demanded) row for each name.
    prepared["_skill_key"] = prepared["skill_name"].map(normalize_skill_name)
    prepared = prepared.drop_duplicates(subset="_skill_key", keep="first")
    return prepared[list(SKILL_GAP_COLUMNS)].reset_index(drop=True)


@dataclass(frozen=True)
class SkillGapResult:
    """The outcome of comparing one person's skills with one role's needs.

    Attributes
    ----------
    role:
        The target role exactly as the caller named it.
    required, matched, missing:
        Skill frames, each with :data:`SKILL_GAP_COLUMNS`, in the same
        "most demanded first" order as the database returned them. ``matched``
        and ``missing`` always partition ``required``.
    skill_match_pct:
        The unrounded percentage, ``100 * matched / required``, or ``0.0``
        when the role has no required skills at all.
    user_skills:
        The normalized, de-duplicated skills the user typed, in their order.
    recognized_not_required:
        Typed skills that exist in the database but are not required for this
        role. Reported so they are not mistaken for an error, and never
        counted towards the score.
    unrecognized:
        Typed skills that are not in the database at all. Reported, and never
        counted towards the score.
    """

    role: str
    required: pd.DataFrame
    matched: pd.DataFrame
    missing: pd.DataFrame
    skill_match_pct: float
    user_skills: tuple[str, ...]
    recognized_not_required: tuple[str, ...]
    unrecognized: tuple[str, ...]

    @property
    def required_count(self) -> int:
        """How many distinct skills the role requires."""
        return int(len(self.required))

    @property
    def matched_count(self) -> int:
        return int(len(self.matched))

    @property
    def missing_count(self) -> int:
        return int(len(self.missing))

    @property
    def skill_match_text(self) -> str:
        """The match percentage, ready to display (e.g. ``"60%"``)."""
        return format_match_percentage(self.skill_match_pct)

    @property
    def has_user_skills(self) -> bool:
        """``False`` when the user submitted an empty skill list."""
        return bool(self.user_skills)

    @property
    def has_required_skills(self) -> bool:
        """``False`` when no posting for this role lists any skill."""
        return bool(self.required_count)

    @property
    def has_unknown_skills(self) -> bool:
        """``True`` when at least one typed skill is not in the database."""
        return bool(self.unrecognized)


def analyze_skill_gap(
    required_skills: pd.DataFrame | None,
    user_skills: str,
    catalog: pd.DataFrame | None = None,
    role: str = "",
) -> SkillGapResult:
    """Compare the skills a person has with the skills a role requires.

    :param required_skills: the distinct skills the role requires - normally
        ``queries.get_required_skills_for_role(role)``. Only a ``skill_name``
        column is mandatory; see :func:`_coerce_skill_frame`.
    :param user_skills: the person's skills as free text, e.g.
        ``"Python, SQL, Pandas, Git, Docker"``. Split, trimmed and de-duplicated
        by :func:`parse_user_skills`.
    :param catalog: every skill the database knows about - normally
        ``queries.get_skill_catalog()``. Used only to tell a skill the market
        has never heard of apart from a real skill this role does not want.
        When omitted, every typed skill that is not a match is reported as
        "not required for this role" and the "unknown skill" notice never
        fires, because unknownness cannot be established without a catalog.
    :param role: the target role name, carried through to the result for
        display. It plays no part in the calculation.
    :returns: a :class:`SkillGapResult`.

    The percentage is a plain division of two counted quantities::

        matched required skills
        ----------------------  x 100
         total required skills

    Worked example - required ``Python, SQL, Docker, PyTorch, Git`` and typed
    ``Python, SQL, Git`` gives 3 matched out of 5 required, so 60%.

    Behaviour at the edges, none of which is an error:

    * **No skills typed** - everything is reported as missing and the match is
      ``0%``; the caller shows "Please enter at least one skill." instead.
    * **No required skills** - the match is ``0%`` and both lists are empty; the
      caller explains that the role has no recorded requirements.
    * **No overlap at all** - ``0%`` and every required skill is missing.
    * **Full overlap** - ``100%`` and nothing is missing.
    * **Duplicates or odd casing** - collapsed first, so ``python, PYTHON,
      Python`` is one skill and ``Python`` matches ``python``.
    """
    required = _coerce_skill_frame(required_skills)
    typed = parse_user_skills(user_skills)

    typed_keys = {normalize_skill_name(skill) for skill in typed}
    required_keys = {
        normalize_skill_name(name) for name in required["skill_name"].tolist()
    }

    # Every typed skill lands in exactly one of three buckets - matched,
    # recognized-but-not-required, or unknown - so nothing is double-counted
    # and nothing silently disappears.
    canonical_names: dict[str, str] = {}
    if catalog is not None and len(catalog) and "skill_name" in getattr(catalog, "columns", []):
        canonical_names = {
            normalize_skill_name(name): str(name)
            for name in catalog["skill_name"].dropna().tolist()
        }
    # A catalog that carries no names is no catalog at all: without it,
    # unknownness cannot be established, so it must not be claimed.
    has_catalog = bool(canonical_names)

    recognized_not_required: list[str] = []
    unrecognized: list[str] = []
    for skill in typed:
        key = normalize_skill_name(skill)
        if key in required_keys:
            continue  # already shown in the matched list
        if key in canonical_names:
            # Report the database's own spelling, so the person can search for
            # exactly that name rather than guessing why "pandas" was ignored.
            recognized_not_required.append(canonical_names[key])
        elif has_catalog:
            unrecognized.append(skill)
        else:
            recognized_not_required.append(skill)

    is_required = required["skill_name"].map(normalize_skill_name)
    matched = required[is_required.isin(typed_keys)].reset_index(drop=True)
    missing = required[~is_required.isin(typed_keys)].reset_index(drop=True)

    required_count = int(len(required))
    skill_match_pct = (
        100.0 * int(len(matched)) / required_count if required_count else 0.0
    )

    return SkillGapResult(
        role=role,
        required=required,
        matched=matched,
        missing=missing,
        skill_match_pct=skill_match_pct,
        user_skills=tuple(typed),
        recognized_not_required=tuple(recognized_not_required),
        unrecognized=tuple(unrecognized),
    )


def skill_gap_summary_sentence(result: SkillGapResult) -> str:
    """One plain-English line describing the match, e.g. ``"3 of 5 required skills."``"""
    if not result.has_required_skills:
        return "This role has no recorded skill requirements."
    if not result.has_user_skills:
        return (
            f"{result.required_count} required skills for this role - "
            "enter your skills above to score them."
        )
    return (
        f"{result.matched_count} of {result.required_count} required skills "
        f"({result.skill_match_text} skill match)."
    )


def skill_gap_kpi_cards(result: SkillGapResult) -> list[dict[str, str]]:
    """Build the three count cards shown under the big match percentage.

    Same shape as :func:`kpi_cards`, so :func:`render_kpis` draws them with the
    identical dark styling. Colours carry meaning here: green for skills already
    held, amber for the gap to close, blue for the total.
    """
    return [
        {
            "label": "Matched Skills",
            "value": f"{result.matched_count:,}",
            "sub": "required skills you already have",
            "accent": SUCCESS,
        },
        {
            "label": "Missing Skills",
            "value": f"{result.missing_count:,}",
            "sub": "required skills to learn",
            "accent": WARNING,
        },
        {
            "label": "Required Skills",
            "value": f"{result.required_count:,}",
            "sub": "distinct skills for this role",
            "accent": ACCENT,
        },
    ]


# =============================================================================
# RENDERERS - Streamlit layout
# =============================================================================


def render_header(title: str, subtitle: str, eyebrow: str = "Recruiting analytics") -> None:
    """Draw the page header above the tabs."""
    st.markdown(
        f'<div class="dash-eyebrow">{eyebrow}</div>'
        f'<div class="dash-title">{title}</div>'
        f'<div class="dash-subtitle">{subtitle}</div>'
        f'<div class="dash-rule"></div>',
        unsafe_allow_html=True,
    )


def render_section(title: str, caption: str = "") -> None:
    """Draw a section heading, optionally with a one-line explanation."""
    st.markdown(
        f'<div class="section-title">{title}</div>'
        + (f'<div class="section-caption">{caption}</div>' if caption else ""),
        unsafe_allow_html=True,
    )


def render_database_error(error: BaseException) -> None:
    """Explain a database failure without leaking secrets or a traceback.

    The headline says what to do; the technical reason is shown as a
    credential-redacted single line. ``st.exception`` is deliberately not
    used, because a traceback would print connection details to the browser.
    """
    st.markdown('<div class="dash-rule"></div>', unsafe_allow_html=True)
    st.error(
        "**Cannot read the PostgreSQL database.** The dashboard needs a running "
        "local PostgreSQL instance and the `DB_*` settings in a `.env` file in "
        "the project root.",
        icon=":material/cloud_off:",
    )
    st.caption(f"Reason reported by the data layer: {redact(error)}")
    st.markdown(
        "1. Start the local PostgreSQL service.\n"
        "2. `copy .env.example .env` and fill in `DB_PASSWORD`.\n"
        "3. Confirm `database/schema.sql` and `database/seed.sql` have been loaded.\n"
        "4. Reload this page."
    )
    st.caption(
        "Credentials are read from the environment and are never displayed, logged "
        "or sent to the browser."
    )


def reset_filters() -> None:
    """Clear every filter widget. Wired to the sidebar's Reset Filters button."""
    for key in FILTER_KEYS:
        st.session_state.pop(key, None)


def render_sidebar(jobs: pd.DataFrame) -> dict[str, list[Any]]:
    """Render the filter panel and return the active selections.

    Each control is a multiselect populated from the distinct values in the
    database, so no country, industry or role is ever hardcoded. An empty
    selection means "everything".
    """
    selections: dict[str, list[Any]] = {}

    with st.sidebar:
        st.markdown('<div class="sidebar-title">Filters</div>', unsafe_allow_html=True)
        for column, label, key in FILTERS:
            options = sorted(str(value) for value in jobs[column].dropna().unique())
            selections[column] = st.multiselect(
                label,
                options=options,
                key=key,
                format_func=lambda value, col=column: format_filter_value(col, value),
                placeholder=f"All {label.lower()}s",
            )
        st.button(
            "Reset Filters",
            icon=":material/filter_alt_off:",
            on_click=reset_filters,
            width="stretch",
        )
        st.markdown('<div class="sidebar-rule"></div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="sidebar-note">Leaving a filter empty keeps every value. '
            "Filters apply to the KPIs, every chart and the postings table.</div>",
            unsafe_allow_html=True,
        )
    return selections


def render_kpis(cards: Sequence[dict[str, str]]) -> None:
    """Render the KPI cards three per row, which stays readable when narrow."""
    for start in range(0, len(cards), 3):
        row = st.columns(min(3, len(cards) - start), gap="medium")
        for column, card in zip(row, cards[start : start + 3]):
            with column:
                st.markdown(
                    f'<div class="kpi-card" style="border-left-color:{card["accent"]}">'
                    f'<div class="kpi-label">{card["label"]}</div>'
                    f'<div class="kpi-value">{card["value"]}</div>'
                    f'<div class="kpi-sub">{card["sub"]}</div>'
                    f"</div>",
                    unsafe_allow_html=True,
                )


def render_empty_state(hint: str) -> None:
    """Explain that the current filter combination matches nothing."""
    st.markdown(
        f'<div class="chart-empty">No postings match the current filters. {hint}</div>',
        unsafe_allow_html=True,
    )
    st.info("Widen or reset the filters in the sidebar to see results.", icon=":material/filter_alt_off:")


def render_chart(figure: Figure, key: str) -> None:
    """Show a themed, non-animated, responsive Plotly figure.

    ``key`` is required: Streamlit derives an element id from the element type
    and its parameters, so the same chart used in two tabs (the work-mode
    donut, for example) would collide. A unique key per chart is what makes
    reusing a component across tabs safe.
    """
    st.plotly_chart(figure, key=key, config=PLOTLY_CONFIG)


def render_recent_jobs(jobs: pd.DataFrame) -> None:
    """Render the searchable postings table (newest first)."""
    table = build_recent_jobs(jobs)
    if table.empty:
        render_empty_state("There is nothing to list for this selection.")
        return

    left, right = st.columns([2, 3], gap="medium")
    with left:
        search = st.text_input(
            "Search postings",
            placeholder="Job title, company, industry, location…",
            key="recent_search",
            icon=":material/search:",
        )
    with right:
        st.markdown(
            f'<div class="sidebar-note" style="text-align:right;padding-top:1.9rem">'
            f"{len(table):,} postings · newest first · sort any column in the table</div>",
            unsafe_allow_html=True,
        )

    if search:
        needle = search.strip().lower()
        searchable = table[["Job Title", "Company", "Industry", "Location", "Country"]]
        mask = searchable.apply(
            lambda column: column.astype(str).str.lower().str.contains(needle, regex=False)
        ).any(axis=1)
        table = table[mask]

    if table.empty:
        st.info(f"No posting matches “{search}”.", icon=":material/search_off:")
        return

    st.dataframe(
        table.head(RECENT_JOBS_LIMIT),
        hide_index=True,
        height=520,
        column_config={
            "Job Title": st.column_config.TextColumn("Job Title", width="medium"),
            "Company": st.column_config.TextColumn("Company", width="medium"),
            "Industry": st.column_config.TextColumn("Industry"),
            "Posted Date": st.column_config.DateColumn("Posted Date", format="YYYY-MM-DD"),
            "Salary": st.column_config.TextColumn("Salary", width="medium"),
        },
    )


def render_metric_note(text: str) -> None:
    """Small caption under a chart explaining how it was counted."""
    st.caption(text)


# -----------------------------------------------------------------------------
# RENDERERS - SKILL GAP ANALYZER
# -----------------------------------------------------------------------------


def _escape(text: str) -> str:
    """HTML-escape a value before it is injected into a badge span.

    Skill names come from the database and a skill the user typed comes from a
    text box, so neither is trusted to be plain text. Escaping keeps a name like
    ``<script>`` visible as text instead of being rendered as markup.
    """
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_skill_badges(skills: Sequence[str], variant: str, empty_note: str = "") -> None:
    """Render skills as a wrapping row of pill badges.

    :param skills: the skill names to show, in the order given.
    :param variant: one of ``"matched"``, ``"missing"``, ``"extra"`` or
        ``"unknown"`` - it selects the colour, which is the only thing that
        differs between the four lists.
    :param empty_note: shown instead of badges when ``skills`` is empty, so a
        section never renders as a bare heading.
    """
    if not skills:
        if empty_note:
            st.markdown(
                f'<div class="skill-empty">{_escape(empty_note)}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("None.")
        return

    badges = "".join(
        f'<span class="skill-badge skill-badge--{variant}">{_escape(skill)}</span>'
        for skill in skills
    )
    st.markdown(f'<div class="skill-badge-row">{badges}</div>', unsafe_allow_html=True)


def render_skill_gap_hero(result: SkillGapResult) -> None:
    """Draw the large match-percentage card, reusing the KPI card styling.

    The progress bar is plain CSS, not a chart: a two-segment split of "matched
    vs missing" carries no data a number cannot carry, and a bar keeps the tab
    consistent with the KPI cards elsewhere in the dashboard.
    """
    match_pct = max(0.0, min(100.0, float(result.skill_match_pct)))
    role_label = result.role or "No role selected"

    st.markdown(
        f'<div class="gap-hero">'
        f'  <div class="gap-hero-block">'
        f'    <div class="kpi-label">Target Role</div>'
        f'    <div class="gap-hero-role">{_escape(role_label)}</div>'
        f"  </div>"
        f'  <div class="gap-hero-block gap-hero-block--pct">'
        f'    <div class="kpi-label">Skill Match</div>'
        f'    <div class="gap-hero-pct">{result.skill_match_text}</div>'
        f'    <div class="gap-hero-sub">{_escape(skill_gap_summary_sentence(result))}</div>'
        f"  </div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="gap-bar" role="img" '
        f'aria-label="{result.skill_match_text} of the required skills are matched">'
        f'  <div class="gap-bar-fill" style="width:{match_pct:.2f}%"></div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def render_required_skills_table(required: pd.DataFrame) -> None:
    """Show every required skill with how widely the role asks for it."""
    if required.empty:
        st.info(
            "No skill requirements are recorded for this role in the database.",
            icon=":material/info:",
        )
        return

    table = required.rename(
        columns={
            "skill_name": "Skill",
            "skill_category": "Category",
            "job_count": "Postings Requiring",
            "pct_of_role_jobs": "Percentage of Role",
        }
    )
    st.dataframe(
        table,
        hide_index=True,
        height=420,
        column_config={
            "Skill": st.column_config.TextColumn("Skill", width="medium"),
            "Postings Requiring": st.column_config.NumberColumn("Postings Requiring", format="%d"),
            "Percentage of Role": st.column_config.NumberColumn("Percentage of Role", format="%.0f%%"),
        },
    )
    st.caption(
        "Percentages are the share of this role's postings that list the skill, so "
        "they overlap and do not add up to 100%. Skills are ordered by how widely "
        "the role asks for them."
    )


def render_skill_gap_result(result: SkillGapResult) -> None:
    """Draw the whole analysis: hero, counts, matched, missing, required.

    Every branch below is a normal state, not an error: an unknown skill, a
    role with no requirements and a 0% match all still produce a full, readable
    report.
    """
    render_skill_gap_hero(result)
    st.markdown('<div class="dash-rule"></div>', unsafe_allow_html=True)

    if not result.has_required_skills:
        st.warning(
            f"No skills are recorded for **{result.role or 'this role'}** in the "
            "database, so there is nothing to match against. Pick another role, "
            "or check that job_skills has entries for its postings.",
            icon=":material/help:",
        )
        return

    if not result.has_user_skills:
        st.info("Please enter at least one skill.", icon=":material/edit_note:")
        return

    if result.matched_count == 0:
        st.warning(
            "0% skill match. None of the skills you listed is required for this "
            f"role, so all {result.required_count} required skills are missing.",
            icon=":material/trending_flat:",
        )
    elif result.missing_count == 0:
        st.success(
            f"100% skill match. You already have every one of the "
            f"{result.required_count} skills this role requires.",
            icon=":material/task_alt:",
        )
    elif result.skill_match_pct < 50:
        st.info(
            f"{result.skill_match_text} skill match. {result.missing_count} of the "
            f"{result.required_count} required skills are still missing.",
            icon=":material/trending_up:",
        )

    if result.has_unknown_skills:
        st.warning(
            "Some entered skills were not found in the job-market skill database.",
            icon=":material/search_off:",
        )
        render_skill_badges(list(result.unrecognized), "unknown")
        st.caption(
            "These were ignored, because a skill the database has never seen "
            "cannot be a requirement of any role in it."
        )

    render_kpis(skill_gap_kpi_cards(result))

    left, right = st.columns(2, gap="large")
    with left:
        with st.container(border=True):
            render_section(
                "Matched skills",
                "Required by this role, and already in your list.",
            )
            render_skill_badges(
                list(result.matched["skill_name"]),
                "matched",
                empty_note="None of the skills you listed is required for this role.",
            )
    with right:
        with st.container(border=True):
            render_section(
                "Missing skills",
                "Required by this role and not in your list - the gap to close.",
            )
            render_skill_badges(
                list(result.missing["skill_name"]),
                "missing",
                empty_note="Nothing is missing - you cover the whole requirement set.",
            )

    if result.recognized_not_required:
        with st.container(border=True):
            render_section(
                "Also in your list, not required for this role",
                "Known skills that this role does not ask for. They do not affect the score.",
            )
            render_skill_badges(list(result.recognized_not_required), "extra")

    with st.container(border=True):
        render_section(
            "Required skills",
            skill_gap_summary_sentence(result),
        )
        render_required_skills_table(result.required)

    st.caption(
        "Skill match % = matched required skills ÷ total required skills × 100. "
        "Names are compared after trimming, lower-casing and removing duplicates; "
        "no fuzzy matching or synonym expansion is applied, so a skill only counts "
        "when the database stores that exact name."
    )


# =============================================================================
# CHARTS
# =============================================================================


def _bar_counts(
    counts: pd.DataFrame,
    column: str,
    *,
    horizontal: bool,
    color: str = ACCENT,
) -> Figure:
    """Shared bar chart for a counted categorical column."""
    if horizontal:
        # Plotly draws the first category at the bottom, so reversing the
        # ascending frame puts the biggest bar on top.
        ordered = counts.sort_values("job_count", ascending=True)
        figure = px.bar(
            ordered,
            x="job_count",
            y=column,
            orientation="h",
            text="job_count",
            color_discrete_sequence=[color],
            labels={"job_count": "Jobs", column: ""},
            custom_data=["job_count"],
        )
        figure.update_traces(
            texttemplate="%{x:,.0f}",
            textposition="outside",
            cliponaxis=False,
            hovertemplate=f"<b>%{{y}}</b><br>Jobs: %{{customdata[0]:,.0f}}<extra></extra>",
        )
    else:
        ordered = counts.sort_values("job_count", ascending=False)
        figure = px.bar(
            ordered,
            x=column,
            y="job_count",
            text="job_count",
            color_discrete_sequence=[color],
            labels={"job_count": "Jobs", column: ""},
            custom_data=["job_count"],
        )
        figure.update_traces(
            texttemplate="%{y:,.0f}",
            textposition="outside",
            cliponaxis=False,
            hovertemplate=f"<b>%{{x}}</b><br>Jobs: %{{customdata[0]:,.0f}}<extra></extra>",
        )
    return figure


def chart_job_counts(
    frame: pd.DataFrame,
    column: str,
    *,
    top: int | None = None,
    horizontal: bool = False,
) -> Figure:
    """Bar chart of postings per value of ``column``."""
    return apply_figure_theme(
        _bar_counts(top_values(frame, column, top), column, horizontal=horizontal),
        height=380,
    )


def chart_work_mode_mix(frame: pd.DataFrame) -> Figure:
    """Donut of the remote / hybrid / onsite split."""
    counts = top_values(frame, "work_mode")
    colors = [WORK_MODE_COLORS.get(str(mode), TEXT_MUTED) for mode in counts["work_mode"]]
    figure = px.pie(
        counts,
        names="work_mode",
        values="job_count",
        hole=0.55,
        color_discrete_sequence=colors,
        labels={"work_mode": "", "job_count": "Jobs"},
        custom_data=["job_count"],
    )
    figure.update_traces(
        textposition="inside",
        textinfo="percent",
        textfont=dict(size=12, color="#0e1117"),
        hovertemplate="<b>%{label}</b><br>Jobs: %{customdata[0]:,.0f}<extra></extra>",
    )
    return apply_figure_theme(figure, height=380, show_legend=True)


def chart_monthly_postings(frame: pd.DataFrame) -> Figure:
    """Line chart of postings per month - the hiring-trend view."""
    monthly = monthly_postings(frame)
    figure = px.line(
        monthly,
        x="month",
        y="job_count",
        markers=True,
        color_discrete_sequence=[ACCENT],
        labels={"month": "Month", "job_count": "Jobs posted"},
        custom_data=["job_count"],
    )
    figure.update_traces(
        line=dict(width=2.5),
        marker=dict(size=7),
        hovertemplate="<b>%{x|%b %Y}</b><br>Jobs: %{customdata[0]:,.0f}<extra></extra>",
    )
    return apply_figure_theme(figure, height=320)


def chart_top_skills(demand: pd.DataFrame, top: int = 10) -> Figure:
    """Horizontal bars for the most demanded skills, labelled with their share."""
    if demand.empty:
        return _empty_figure("No skill requirement in this selection")
    top_demand = demand.head(top).sort_values("job_count", ascending=True)
    figure = px.bar(
        top_demand,
        x="job_count",
        y="skill_name",
        orientation="h",
        text="pct_of_jobs",
        color_discrete_sequence=[ACCENT],
        labels={"job_count": "Jobs requiring the skill", "skill_name": ""},
        custom_data=["skill_category", "job_count", "company_count", "pct_of_jobs"],
    )
    figure.update_traces(
        texttemplate="%{text:.0f}%",
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "<b>%{y}</b><br>Category: %{customdata[0]}"
            "<br>Jobs: %{customdata[1]:,.0f} of %{x:,.0f}"
            "<br>Companies: %{customdata[2]:,.0f}"
            "<br>Share of jobs: %{customdata[3]:.1f}%<extra></extra>"
        ),
    )
    return apply_figure_theme(figure, height=400)


def chart_skills_by_category(by_category: pd.DataFrame) -> Figure:
    """Bar chart of skill demand per category."""
    if by_category.empty:
        return _empty_figure("No skill requirement in this selection")
    ordered = by_category.sort_values("job_requirements", ascending=True)
    figure = px.bar(
        ordered,
        x="job_requirements",
        y="skill_category",
        orientation="h",
        text="skill_count",
        color_discrete_sequence=[SEQUENTIAL[2]],
        labels={"job_requirements": "Skill requirements", "skill_category": ""},
        custom_data=["skill_count", "pct_of_demand"],
    )
    figure.update_traces(
        texttemplate="%{customdata[0]:,.0f} skills",
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "<b>%{y}</b><br>Skill requirements: %{x:,.0f}"
            "<br>Distinct skills: %{customdata[0]:,.0f}"
            "<br>Share of demand: %{customdata[1]:.1f}%<extra></extra>"
        ),
    )
    return apply_figure_theme(figure, height=380)


def chart_salary_range_by_role(salary_by_role: pd.DataFrame, unit: tuple[str, str]) -> Figure:
    """Advertised salary range per role, for ONE currency and period.

    The bar is the average midpoint and the whiskers are the average low and
    high of the advertised range, so the reader sees the spread, not just a
    single number. Only rows matching ``unit`` are drawn - amounts from
    different currencies or pay periods are never placed on the same axis.
    """
    scoped = _scoped_salary(salary_by_role, unit)
    if scoped.empty:
        return _empty_figure("No disclosed salary for this currency and period")

    ordered = scoped.sort_values("avg_salary_midpoint", ascending=True)
    figure = px.bar(
        ordered,
        x="avg_salary_midpoint",
        y="role",
        orientation="h",
        color_discrete_sequence=[ACCENT],
        labels={"avg_salary_midpoint": f"Average advertised salary ({unit_label(unit)})", "role": ""},
        custom_data=["currency", "salary_period", "jobs_with_salary",
                     "avg_salary_min", "avg_salary_max"],
    )
    # The whiskers are applied with update_traces rather than px.bar(error_y=...):
    # passing a dict for error_y to px.bar makes Plotly measure the dict itself
    # against the data length and fail.
    figure.update_traces(
        error_y=dict(
            type="data",
            symmetric=False,
            array=(ordered["avg_salary_max"] - ordered["avg_salary_midpoint"]).clip(lower=0),
            arrayminus=(ordered["avg_salary_midpoint"] - ordered["avg_salary_min"]).clip(lower=0),
            color=BORDER,
            thickness=1.2,
            width=6,
        ),
        hovertemplate=(
            "<b>%{y}</b><br>Unit: %{customdata[0]} %{customdata[1]}"
            "<br>Postings: %{customdata[2]:,.0f}"
            "<br>Average range: %{customdata[3]:,.0f} – %{customdata[4]:,.0f}"
            "<extra></extra>"
        ),
    )
    return apply_figure_theme(figure, height=max(320, 26 * len(ordered) + 120))


def chart_average_salary_by_role(salary_by_role: pd.DataFrame, unit: tuple[str, str]) -> Figure:
    """Average low and high salary per role, for ONE currency and period."""
    scoped = _scoped_salary(salary_by_role, unit)
    if scoped.empty:
        return _empty_figure("No disclosed salary for this currency and period")

    reshaped = scoped.melt(
        id_vars=["role", "currency", "salary_period", "jobs_with_salary"],
        value_vars=["avg_salary_min", "avg_salary_max"],
        var_name="bound",
        value_name="amount",
    )
    reshaped["bound"] = reshaped["bound"].map(
        {"avg_salary_min": "Average minimum", "avg_salary_max": "Average maximum"}
    )
    figure = px.bar(
        reshaped,
        x="role",
        y="amount",
        color="bound",
        barmode="group",
        color_discrete_sequence=[SEQUENTIAL[0], ACCENT],
        labels={"role": "", "amount": f"Salary ({unit_label(unit)})", "bound": ""},
        custom_data=["currency", "salary_period", "jobs_with_salary"],
    )
    figure.update_traces(
        texttemplate="%{y:,.0f}",
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "<b>%{x}</b><br>%{fullData.name}"
            "<br>Unit: %{customdata[0]} %{customdata[1]}"
            "<br>Postings: %{customdata[2]:,.0f}<extra></extra>"
        ),
    )
    return apply_figure_theme(figure, height=400, show_legend=True)


def chart_salary_market_split(jobs: pd.DataFrame) -> Figure:
    """How many postings disclose a salary, per currency AND period.

    This chart counts postings, never amounts, so it is safe to show every
    currency side by side: a bar of "INR · YEARLY" and a bar of "USD · HOURLY"
    compare disclosure volume, not pay.
    """
    if jobs.empty:
        return _empty_figure("No postings to compare")

    disclosed = jobs[jobs["salary_min"].notna() & jobs["salary_max"].notna()].copy()
    if disclosed.empty:
        return _empty_figure("No posting in this selection discloses a salary")

    disclosed["unit"] = disclosed["currency"] + " · " + disclosed["salary_period"]
    counts = (
        disclosed.groupby("unit", as_index=False)
        .agg(job_count=("job_id", "nunique"), roles=("job_title", "nunique"))
        .sort_values("job_count", ascending=True)
    )
    figure = px.bar(
        counts,
        x="job_count",
        y="unit",
        orientation="h",
        text="job_count",
        color_discrete_sequence=[SEQUENTIAL[1]],
        labels={"job_count": "Postings disclosing a salary", "unit": ""},
        custom_data=["roles"],
    )
    figure.update_traces(
        texttemplate="%{x:,.0f}",
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "<b>%{y}</b><br>Postings: %{x:,.0f}<br>Distinct roles: %{customdata[0]:,.0f}"
            "<extra></extra>"
        ),
    )
    return apply_figure_theme(figure, height=max(240, 30 * len(counts) + 120))


def chart_salary_distribution(salary_by_role: pd.DataFrame, unit: tuple[str, str]) -> Figure:
    """Distribution of average role salaries within ONE currency and period."""
    scoped = _scoped_salary(salary_by_role, unit)
    if scoped.empty:
        return _empty_figure("No disclosed salary for this currency and period")

    figure = px.histogram(
        scoped,
        x="avg_salary_midpoint",
        nbins=min(12, max(3, len(scoped))),
        color_discrete_sequence=[ACCENT],
        labels={"avg_salary_midpoint": f"Average advertised salary ({unit_label(unit)})"},
    )
    figure.update_traces(
        hovertemplate=(
            f"Average salary ({unit_label(unit)})<br>Range: %{{x:,.0f}}"
            "<br>Roles in bin: %{y:,.0f}<extra></extra>"
        )
    )
    return apply_figure_theme(figure, height=320)


def chart_experience_distribution(distribution: pd.DataFrame) -> Figure:
    """Bar chart of the seniority split, labelled with each band's share."""
    if distribution.empty:
        return _empty_figure("No postings to summarise")

    figure = px.bar(
        distribution,
        x="seniority_band",
        y="jobs_posted",
        text="pct_of_all_jobs",
        color_discrete_sequence=[ACCENT],
        labels={"seniority_band": "", "jobs_posted": "Jobs posted"},
        custom_data=["pct_of_all_jobs", "companies_hiring"],
    )
    figure.update_traces(
        texttemplate="%{customdata[0]:.1f}%",
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "<b>%{x}</b><br>Jobs: %{y:,.0f}"
            "<br>Share: %{customdata[0]:.1f}%"
            "<br>Companies hiring: %{customdata[1]:,.0f}<extra></extra>"
        ),
    )
    return apply_figure_theme(figure, height=360)


def _scoped_salary(salary_by_role: pd.DataFrame, unit: tuple[str, str]) -> pd.DataFrame:
    """Return only the rows of ``salary_by_role`` belonging to ``unit``."""
    if salary_by_role.empty:
        return salary_by_role
    currency, period = unit
    return salary_by_role[
        (salary_by_role["currency"] == currency) & (salary_by_role["salary_period"] == period)
    ].copy()


def _empty_figure(message: str) -> Figure:
    """Placeholder figure used when a filter leaves nothing to draw.

    It carries no data trace at all, just a centred note, so an empty chart
    can never be mistaken for a real value of zero.
    """
    figure = go.Figure()
    figure.add_annotation(
        text=message,
        showarrow=False,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        font=dict(family=FONT_FAMILY, size=13, color=TEXT_MUTED),
    )
    return apply_figure_theme(figure, height=280)


# -----------------------------------------------------------------------------
# RENDERERS - ROLE RECOMMENDATIONS
# -----------------------------------------------------------------------------
# Everything below is presentation. The ranking itself lives in
# ``ml.recommender`` (TF-IDF + cosine similarity); this code only draws the
# DataFrame it returns, so no machine-learning logic sits in the dashboard.


def _badges_html(skills: Sequence[str], variant: str) -> str:
    """One wrapping row of pill badges as raw HTML, for embedding in a card."""
    return "".join(
        f'<span class="skill-badge skill-badge--{variant}">{_escape(skill)}</span>'
        for skill in skills
    )


def _clamp_score(score: float) -> float:
    """Keep a score inside 0-100 before it becomes a bar width with ``%``."""
    return max(0.0, min(100.0, float(score)))


def render_recommendation_card(rank: int, row: pd.Series) -> None:
    """Draw one ranked role as a card: score, matched and missing badges, footer.

    ``role``, ``score``, ``matched_skills``, ``missing_skills`` and
    ``required_skills`` are exactly the five columns the specification asks a
    recommendation to show, plus two counted rows for context. The bar is the
    score on a 0-100 scale - a visual duplicate of the number, never extra data.
    """
    role = str(row["role"])
    score = _clamp_score(row["score"])
    rule_pct = _clamp_score(float(row.get("rule_based_pct", 0.0)))
    matched = tuple(row["matched_skills"])
    missing = tuple(row["missing_skills"])
    required = tuple(row["required_skills"])
    job_count = int(row.get("job_count", 0))
    postings = f"{job_count} posting" if job_count == 1 else f"{job_count} postings"
    required_text = _escape(", ".join(str(skill) for skill in required))

    matched_html = _badges_html(matched, "matched")
    if not matched_html:
        matched_html = '<div class="rec-block-note">Nothing you listed is required by this role.</div>'
    missing_html = _badges_html(missing, "missing")
    if not missing_html:
        missing_html = '<div class="rec-block-note">You already have every required skill.</div>'

    st.markdown(
        f'<div class="rec-card">'
        f'  <div class="rec-head">'
        f'    <div>'
        f'      <div class="rec-rank">Rank #{rank}</div>'
        f'      <div class="rec-role">{_escape(role)}</div>'
        f"    </div>"
        f'    <div class="rec-metric">'
        f'      <div class="rec-score">{score:.1f}<span class="rec-score-unit">%</span></div>'
        f'      <div class="rec-score-label">Skill Similarity Score</div>'
        f"    </div>"
        f"  </div>"
        f'  <div class="rec-bar" role="img" '
        f'aria-label="Skill Similarity Score {score:.1f} percent">'
        f'    <div class="rec-bar-fill" style="width:{score:.2f}%"></div>'
        f"  </div>"
        f'  <div class="rec-columns">'
        f'    <div class="rec-column">'
        f'      <div class="rec-block-label">You have ({len(matched)})</div>'
        f"      {matched_html}"
        f"    </div>"
        f'    <div class="rec-column">'
        f'      <div class="rec-block-label">Missing ({len(missing)})</div>'
        f"      {missing_html}"
        f"    </div>"
        f"  </div>"
        f'  <div class="rec-required">'
        f"    Requires {len(required)} skills · {postings} · Rule-Based Match {rule_pct:.1f}%"
        f"<br><b>Required:</b> {required_text or '(none recorded)'}"
        f"  </div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_market_vocabulary(profiles: pd.DataFrame) -> None:
    """List every skill the market knows, in the database's own spelling.

    Shown when nothing the user typed appears in the vocabulary at all, so the
    tab explains the shape of the marketplace instead of just saying "no match".
    """
    display: dict[str, str] = {}
    if profiles.empty:
        return
    documents = profiles["document"] if "document" in profiles.columns else ()
    spellings = profiles["required_skills"] if "required_skills" in profiles.columns else ()
    for document, shown in zip(documents, spellings):
        for normalized, canonical in zip(document, shown):
            display.setdefault(normalized, canonical)
    if not display:
        return
    skills = [display[key] for key in sorted(display)]
    st.caption("What this market actually knows about:")
    render_skill_badges(skills, "extra")


def render_recommendation_results(
    diag: dict[str, Any] | None,
    profiles: pd.DataFrame,
) -> None:
    """Draw the outcome of one recommendation request.

    :param diag: the dict returned by
        ``ml.recommender.recommend_with_diagnostics``, or ``None`` before the
        user has pressed Recommend Roles.
    :param profiles: the role profiles the recommendations were computed from,
        only used to list the vocabulary when nothing matched.

    Every non-OK branch is a normal state, reported in words rather than
    rendered as a wall of empty cards.
    """
    if diag is None:
        st.info(
            "Enter your skills above, then press **Recommend Roles**. The "
            "ranking is local and deterministic - it is computed here, not sent "
            "anywhere.",
            icon=":material/travel_explore:",
        )
        return

    message = str(diag.get("message", "") or "")
    if diag.get("status") == "no_roles":
        st.info(message or "No job roles are available to recommend.", icon=":material/inbox:")
        return
    if diag.get("status") == "no_skills":
        st.info(message or "Please enter at least one skill.", icon=":material/edit_note:")
        return
    if diag.get("status") == "no_known_skills":
        st.warning(message or "None of your skills are in this market's vocabulary.", icon=":material/search_off:")
        _render_market_vocabulary(profiles)
        return

    unknown = list(diag.get("unknown") or ())
    if unknown:
        st.caption("Not in this market's vocabulary, so ignored:")
        render_skill_badges(unknown, "unknown")

    results = diag.get("results")
    if results is None or results.empty:
        st.info(
            "No role shares any of the skills you listed, so every score is 0.0%. "
            "The rule-based match is the clearer lens for a no-overlap situation.",
            icon=":material/trending_flat:",
        )
        return

    st.markdown(f'<div class="dash-rule"></div>', unsafe_allow_html=True)
    for rank, (_, row) in enumerate(results.iterrows(), start=1):
        render_recommendation_card(rank, row)

    render_method_comparison(diag.get("info") or {})


def render_method_comparison(info: dict[str, Any]) -> None:
    """The side-by-side comparison of the two numbers, inside an expander.

    Pulled from ``ml.recommender.MODEL_COMPARISON`` via the ``info`` dict, so
    the panel's wording lives next to the code that produces the numbers.
    """
    with st.expander("Read the two numbers together", expanded=False):
        for title, body in info.get("comparison", ()):
            st.markdown(f"**{_escape(title)}**")
            st.caption(body)
        st.caption(info.get("no_external_services", ""))


def render_model_information(info: dict[str, Any]) -> None:
    """The "how this recommendation works" panel for the Role Recommendations tab.

    Always states what the number is, what it is not, which data it was fitted
    on, and that no external service is involved - the honesty contract of this
    feature is part of its UI.
    """
    if not info:
        return
    with st.expander("How this recommendation works", expanded=False):
        st.markdown(f"**Method.** {_escape(info.get('method', ''))}")
        st.markdown("Steps:")
        for step in info.get("steps", ()):
            st.markdown(f"- {step}")
        st.warning(
            _escape(info.get("limitations", "")),
            icon=":material/science:",
        )
        st.caption(info.get("no_external_services", ""))

        if info.get("postings_represented"):
            st.caption(
                f"Corpus: {info['role_count']} role profiles built from "
                f"{info['postings_represented']} postings, "
                f"{info['vocabulary_size']} distinct skills."
            )
