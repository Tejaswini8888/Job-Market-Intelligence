"""JOB MARKET INTELLIGENCE & SKILL ANALYTICS - Streamlit dashboard.

Run from the project root::

    .\\.venv\\Scripts\\Activate.ps1
    streamlit run dashboard/app.py

The dashboard owns no database code. Every figure it draws comes from a
function in ``src.data.queries`` through the cached loaders below, so the SQL
for each number exists in exactly one place.

Caching: ``st.cache_data`` memoises the *query results*, not the connection.
Each cached call opens a connection, runs one SELECT, and closes it again, so
no open connection is ever held in the cache and no result is shared between
two users as mutable state.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the project root importable however Streamlit was launched, so
# "from src.data import queries" resolves without PYTHONPATH being set.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import psycopg
import streamlit as st

from dashboard import components as ui
from dashboard.styles import inject_css
from ml.recommender import recommend_with_diagnostics
from src.data import queries
from src.data.database import ConfigurationError, DatabaseConnectionError

# -----------------------------------------------------------------------------
# PAGE CONFIGURATION
# -----------------------------------------------------------------------------
# st.set_page_config must be the first Streamlit command in the script.

st.set_page_config(
    page_title="Job Market Intelligence & Skill Analytics",
    page_icon=":material/analytics:",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()

PAGE_TITLE = "JOB MARKET INTELLIGENCE<br>&amp; SKILL ANALYTICS"
PAGE_SUBTITLE = "Explore job demand, skills, salaries and hiring trends."


# -----------------------------------------------------------------------------
# CACHED DATA ACCESS
# -----------------------------------------------------------------------------
# Each loader is a thin wrapper around one src.data.queries function. The
# database is queried again whenever Streamlit's source-code cache key changes
# (code edit, server restart); filter changes never trigger a query, because
# filtering happens in pandas on the cached frames.


@st.cache_data(show_spinner="Reading PostgreSQL …")
def load_jobs() -> pd.DataFrame:
    """Every posting with its company details (the base for filters and KPIs)."""
    return queries.get_all_jobs()


@st.cache_data(show_spinner=False)
def load_job_skill_links() -> pd.DataFrame:
    """The job <-> skill junction table, so demand can be recounted per filter."""
    return queries.get_job_skill_links()


@st.cache_data(show_spinner=False)
def load_market_top_skills() -> pd.DataFrame:
    """Market-wide top skills straight from the data layer's own query."""
    return queries.get_top_skills(limit=10)


@st.cache_data(show_spinner=False)
def load_salary_by_role() -> pd.DataFrame:
    """Average salary per role, already grouped by currency and pay period."""
    return queries.get_average_salary_by_role()


@st.cache_data(show_spinner=False)
def load_experience_distribution() -> pd.DataFrame:
    """Seniority split of the whole market, straight from the data layer."""
    return queries.get_experience_distribution()


@st.cache_data(show_spinner=False)
def load_table_counts() -> pd.DataFrame:
    """Row counts per table, used for the "of N in the market" KPI caption."""
    return queries.get_table_row_counts()


@st.cache_data(show_spinner=False)
def load_job_roles() -> pd.DataFrame:
    """Every advertised job title, for the Skill Gap Analyzer's role dropdown."""
    return queries.get_available_job_roles()


@st.cache_data(show_spinner=False)
def load_skill_catalog() -> pd.DataFrame:
    """Every skill the database knows, used to spot skills that are not in it."""
    return queries.get_skill_catalog()


@st.cache_data(show_spinner=False)
def load_required_skills(role: str) -> pd.DataFrame:
    """The skills required by one role.

    Cached on the role string, so re-analysing the same role costs nothing while
    a different role still runs its own single parameterised SELECT. The cache
    holds query results, never a connection.
    """
    return queries.get_required_skills_for_role(role)


@st.cache_data(show_spinner=False)
def load_recommendation_profiles() -> pd.DataFrame:
    """One aggregate profile per job role, for the Role Recommendations tab.

    A thin wrapper around the ML package's own loader, which reuses the data
    layer (``jobs -> job_skills -> skills``); no part of this dashboard owns a
    database connection.
    """
    from ml.recommender import load_role_profiles

    return load_role_profiles()


# -----------------------------------------------------------------------------
# TAB: OVERVIEW
# -----------------------------------------------------------------------------


def tab_overview(jobs: pd.DataFrame, links: pd.DataFrame, market_jobs: int) -> None:
    """KPI cards plus a short read of the current selection."""
    filtered = ui.apply_filters(jobs, st.session_state["selections"])

    if filtered.empty:
        ui.render_empty_state("No KPI can be shown for this selection.")
        return

    filtered_links = links[links["job_id"].isin(set(filtered["job_id"]))]
    ui.render_kpis(ui.kpi_cards(filtered, filtered_links, market_jobs))

    left, right = st.columns(2, gap="large")
    with left:
        with st.container(border=True):
            ui.render_section("Jobs by role", "Which roles are hiring in this selection.")
            ui.render_chart(ui.chart_job_counts(filtered, "job_title", top=8, horizontal=True), key="overview_roles")
    with right:
        with st.container(border=True):
            ui.render_section("Most demanded skills", "Top 10 skills and the share of jobs that require them.")
            ui.render_chart(ui.chart_top_skills(ui.build_skill_demand(links, filtered)), key="overview_top_skills")

    bottom_left, bottom_right = st.columns([1, 2], gap="large")
    with bottom_left:
        with st.container(border=True):
            ui.render_section("Work arrangement", "Remote, hybrid and onsite split.")
            ui.render_chart(ui.chart_work_mode_mix(filtered), key="overview_work_mode")
    with bottom_right:
        with st.container(border=True):
            ui.render_section("Latest postings", "Five most recent roles in this selection.")
            recent = ui.build_recent_jobs(filtered).head(5)
            st.dataframe(
                recent[["Job Title", "Company", "Location", "Work Mode", "Salary", "Currency", "Posted Date"]],
                hide_index=True,
                column_config={
                    "Posted Date": st.column_config.DateColumn("Posted Date", format="YYYY-MM-DD")
                },
            )


# -----------------------------------------------------------------------------
# TAB: JOB DEMAND
# -----------------------------------------------------------------------------


def tab_job_demand(jobs: pd.DataFrame) -> None:
    """Four demand views plus the posting trend."""
    filtered = ui.apply_filters(jobs, st.session_state["selections"])
    if filtered.empty:
        ui.render_empty_state("No demand data to chart for this selection.")
        return

    top_row = st.columns(2, gap="large")
    with top_row[0]:
        with st.container(border=True):
            ui.render_section("Jobs by role", "Number of postings per advertised job title.")
            ui.render_chart(ui.chart_job_counts(filtered, "job_title", top=12, horizontal=True), key="demand_roles")
    with top_row[1]:
        with st.container(border=True):
            ui.render_section("Jobs by country", "Where the postings are based.")
            ui.render_chart(ui.chart_job_counts(filtered, "country"), key="demand_country")

    second_row = st.columns(2, gap="large")
    with second_row[0]:
        with st.container(border=True):
            ui.render_section("Jobs by work mode", "Remote, hybrid and onsite split.")
            ui.render_chart(ui.chart_work_mode_mix(filtered), key="demand_work_mode")
    with second_row[1]:
        with st.container(border=True):
            ui.render_section("Jobs by industry", "Industries hiring in this selection.")
            ui.render_chart(ui.chart_job_counts(filtered, "industry", top=12, horizontal=True), key="demand_industry")

    with st.container(border=True):
        ui.render_section(
            "Hiring trend",
            "Postings published per month, oldest first.",
        )
        ui.render_chart(ui.chart_monthly_postings(filtered), key="demand_trend")
        ui.render_metric_note("Counts distinct postings, so a job with two skills is counted once.")


# -----------------------------------------------------------------------------
# TAB: SKILL DEMAND
# -----------------------------------------------------------------------------


def tab_skill_demand(jobs: pd.DataFrame, links: pd.DataFrame, market_skills: pd.DataFrame) -> None:
    """Filter-aware skill demand, next to the market-wide ranking."""
    filtered = ui.apply_filters(jobs, st.session_state["selections"])
    if filtered.empty:
        ui.render_empty_state("No skill demand to chart for this selection.")
        return

    demand = ui.build_skill_demand(links, filtered)
    by_category = ui.build_skills_by_category(demand)

    top_row = st.columns(2, gap="large")
    with top_row[0]:
        with st.container(border=True):
            ui.render_section("Top 10 most demanded skills", "Labels show the share of postings that require the skill.")
            ui.render_chart(ui.chart_top_skills(demand), key="skills_top")
    with top_row[1]:
        with st.container(border=True):
            ui.render_section("Skills by category", "Skill requirements grouped by category.")
            ui.render_chart(ui.chart_skills_by_category(by_category), key="skills_category")

    with st.container(border=True):
        ui.render_section(
            "Skill demand table",
            f"{len(demand):,} skills required by the {len(filtered):,} selected postings.",
        )
        table = demand.rename(
            columns={
                "skill_name": "Skill",
                "skill_category": "Category",
                "job_count": "Job Count",
                "company_count": "Company Count",
                "pct_of_jobs": "Percentage of Jobs",
            }
        )
        st.dataframe(
            table,
            hide_index=True,
            height=420,
            column_config={
                "Job Count": st.column_config.NumberColumn("Job Count", format="%d"),
                "Company Count": st.column_config.NumberColumn("Company Count", format="%d"),
                "Percentage of Jobs": st.column_config.NumberColumn("Percentage of Jobs", format="%.1f%%"),
            },
        )

    with st.expander("Market-wide top 10 skills (all postings, unfiltered)"):
        st.caption(
            "Straight from the data layer's get_top_skills() query, so it stays "
            "constant while the sidebar filters change."
        )
        st.dataframe(
            market_skills.rename(
                columns={
                    "skill_name": "Skill",
                    "skill_category": "Category",
                    "job_count": "Job Count",
                    "company_count": "Company Count",
                    "pct_of_all_jobs": "Percentage of Jobs",
                }
            ),
            hide_index=True,
        )


# -----------------------------------------------------------------------------
# TAB: SALARY ANALYTICS
# -----------------------------------------------------------------------------


def tab_salary_analytics(jobs: pd.DataFrame, salary_by_role: pd.DataFrame) -> None:
    """Salary analysis, always scoped to a single currency and pay period.

    Nothing on this tab adds or ranks amounts from different currencies or
    different pay periods. The cross-currency view counts postings only.
    """
    filtered = ui.apply_filters(jobs, st.session_state["selections"])
    if filtered.empty:
        ui.render_empty_state("No salary data to analyse for this selection.")
        return

    units = ui.salary_units(filtered)
    if not units:
        ui.render_empty_state("No posting in this selection discloses a salary.")
        return

    labels = [ui.unit_label(unit) for unit in units]
    default_index = labels.index("INR · YEARLY") if "INR · YEARLY" in labels else 0
    chosen_label = st.selectbox(
        "Salary unit",
        labels,
        index=default_index,
        key="salary_unit",
        help=(
            "Amounts are only ever compared inside one currency and one pay period. "
            "There is no exchange-rate table in this database, so INR, USD, GBP, "
            "EUR, AUD, CAD and SGD are never added together or ranked against "
            "each other."
        ),
    )
    unit = units[labels.index(chosen_label)]

    # Recompute the per-role aggregate for the filtered selection so the charts
    # and the table below cannot advertise a role that has no posting here.
    # Market-wide figures are still used, but only as a labelled reference.
    scoped_salary_by_role = ui.build_salary_by_role(filtered)
    selection_label = (
        "the whole market"
        if len(filtered) == len(jobs)
        else f"the {len(filtered)} postings in the current selection"
    )

    st.info(
        f"Showing **{unit[0]}** amounts per **{unit[1].lower()}** only, "
        f"averaged across {selection_label}. "
        "Switch the unit above to compare a different currency or pay period.",
        icon=":material/currency_exchange:",
    )

    top_row = st.columns(2, gap="large")
    with top_row[0]:
        with st.container(border=True):
            ui.render_section(
                "Salary range by role",
                f"Average advertised range for {selection_label}, {unit[0]} per {unit[1].lower()}.",
            )
            ui.render_chart(ui.chart_salary_range_by_role(scoped_salary_by_role, unit), key="salary_range")
    with top_row[1]:
        with st.container(border=True):
            ui.render_section(
                "Average salary by role",
                f"Average minimum and maximum for {selection_label}, {unit[0]} per {unit[1].lower()}.",
            )
            ui.render_chart(
                ui.chart_average_salary_by_role(scoped_salary_by_role, unit), key="salary_average"
            )

    second_row = st.columns(2, gap="large")
    with second_row[0]:
        with st.container(border=True):
            ui.render_section(
                "Salary disclosure by currency",
                "Postings per currency and period. This counts postings, never amounts.",
            )
            ui.render_chart(ui.chart_salary_market_split(filtered), key="salary_split")
    with second_row[1]:
        with st.container(border=True):
            ui.render_section(
                "Salary distribution",
                f"How average role salaries spread within {unit[0]} {unit[1].lower()}.",
            )
            ui.render_chart(
                ui.chart_salary_distribution(scoped_salary_by_role, unit), key="salary_distribution"
            )

    with st.container(border=True):
        ui.render_section(
            f"Average salary by role · {unit[0]} · {unit[1]}",
            f"Every figure below is scoped to the selected unit and to {selection_label}.",
        )
        scoped = scoped_salary_by_role[
            (scoped_salary_by_role["currency"] == unit[0])
            & (scoped_salary_by_role["salary_period"] == unit[1])
        ]
        if scoped.empty:
            st.info(f"No role in this selection discloses a {unit[0]} {unit[1].lower()} salary.")
        else:
            st.dataframe(
                scoped.rename(
                    columns={
                        "role": "Role",
                        "currency": "Currency",
                        "salary_period": "Salary Period",
                        "jobs_with_salary": "Postings",
                        "company_count": "Companies",
                        "avg_salary_min": "Average Min",
                        "avg_salary_max": "Average Max",
                        "avg_salary_midpoint": "Average Midpoint",
                        "lowest_salary_min": "Lowest Advertised",
                        "highest_salary_max": "Highest Advertised",
                    }
                )[
                    [
                        "Role",
                        "Currency",
                        "Salary Period",
                        "Postings",
                        "Companies",
                        "Average Min",
                        "Average Max",
                        "Average Midpoint",
                        "Lowest Advertised",
                        "Highest Advertised",
                    ]
                ],
                hide_index=True,
                column_config={
                    column: st.column_config.NumberColumn(column, format="%.0f")
                    for column in (
                        "Average Min",
                        "Average Max",
                        "Average Midpoint",
                        "Lowest Advertised",
                        "Highest Advertised",
                    )
                },
            )
        st.caption(
            "Amounts are shown in the currency and pay period of their own row. "
            "A yearly figure and a daily figure are never added together."
        )

    # Market-wide reference, collapsed by default so it cannot be mistaken for
    # the filtered view above. The aggregates come straight from SQL, so they
    # stay available even when the selection is too narrow to average.
    with st.expander("Market-wide salary benchmark (all postings, unfiltered)", expanded=False):
        market = salary_by_role[
            (salary_by_role["currency"] == unit[0])
            & (salary_by_role["salary_period"] == unit[1])
        ]
        if market.empty:
            st.info(
                f"No role across the whole market discloses a {unit[0]} "
                f"{unit[1].lower()} salary either."
            )
        else:
            ui.render_chart(
                ui.chart_salary_range_by_role(salary_by_role, unit), key="salary_range_market"
            )
            ui.render_chart(
                ui.chart_salary_distribution(salary_by_role, unit), key="salary_distribution_market"
            )
            st.dataframe(
                market[["role", "jobs_with_salary", "company_count", "avg_salary_midpoint"]].rename(
                    columns={
                        "role": "Role",
                        "jobs_with_salary": "Postings",
                        "company_count": "Companies",
                        "avg_salary_midpoint": "Average Midpoint",
                    }
                ),
                hide_index=True,
                column_config={
                    "Average Midpoint": st.column_config.NumberColumn(
                        f"Average Midpoint ({unit[0]} {unit[1].lower()})", format="%.0f"
                    )
                },
            )


# -----------------------------------------------------------------------------
# TAB: EXPERIENCE ANALYTICS
# -----------------------------------------------------------------------------


def tab_experience(jobs: pd.DataFrame, market_distribution: pd.DataFrame) -> None:
    """Seniority split of the selection, with the market-wide split alongside."""
    filtered = ui.apply_filters(jobs, st.session_state["selections"])
    if filtered.empty:
        ui.render_empty_state("No experience data to summarise for this selection.")
        return

    distribution = ui.experience_distribution(filtered)

    left, right = st.columns([3, 2], gap="large")
    with left:
        with st.container(border=True):
            ui.render_section(
                "Experience distribution",
                "Entry, junior, mid, senior and staff levels in this selection.",
            )
            ui.render_chart(ui.chart_experience_distribution(distribution), key="experience_distribution")
    with right:
        with st.container(border=True):
            ui.render_section("Detail", "Job count, share and employers per band.")
            st.dataframe(
                distribution.rename(
                    columns={
                        "seniority_band": "Seniority Band",
                        "jobs_posted": "Job Count",
                        "companies_hiring": "Companies Hiring",
                        "pct_of_all_jobs": "Percentage of Jobs",
                        "avg_experience_midpoint_years": "Avg Years (Midpoint)",
                    }
                ),
                hide_index=True,
                column_config={
                    "Job Count": st.column_config.NumberColumn("Job Count", format="%d"),
                    "Companies Hiring": st.column_config.NumberColumn("Companies Hiring", format="%d"),
                    "Percentage of Jobs": st.column_config.NumberColumn("Percentage of Jobs", format="%.1f%%"),
                    "Avg Years (Midpoint)": st.column_config.NumberColumn("Avg Years (Midpoint)", format="%.2f"),
                },
            )

    with st.expander("Market-wide seniority split (all postings, unfiltered)"):
        st.caption("Straight from the data layer's get_experience_distribution() query.")
        st.dataframe(
            market_distribution.rename(
                columns={
                    "seniority_band": "Seniority Band",
                    "jobs_posted": "Job Count",
                    "companies_hiring": "Companies Hiring",
                    "pct_of_all_jobs": "Percentage of Jobs",
                    "avg_experience_midpoint_years": "Avg Years (Midpoint)",
                }
            ),
            hide_index=True,
        )


# -----------------------------------------------------------------------------
# TAB: RECENT JOBS
# -----------------------------------------------------------------------------


def tab_recent_jobs(jobs: pd.DataFrame) -> None:
    """Searchable, sortable postings table, newest first."""
    filtered = ui.apply_filters(jobs, st.session_state["selections"])
    ui.render_section(
        "Recent jobs",
        "Every posting in the current selection, newest first. The table itself is "
        "sortable and the search box matches title, company, industry, location and country.",
    )
    ui.render_recent_jobs(filtered)


# -----------------------------------------------------------------------------
# TAB: SKILL GAP ANALYZER
# -----------------------------------------------------------------------------


def tab_skill_gap(roles: pd.DataFrame, catalog: pd.DataFrame) -> None:
    """Compare the user's skills with the skills one target role requires.

    The rule is deliberately simple and is shown on screen, not hidden::

        skill match %  =  matched required skills
                           ----------------------  x 100
                            total required skills

    Required skills come from PostgreSQL (jobs -> job_skills -> skills), matched
    against ``job_title`` case-insensitively. Nothing is hardcoded and nothing is
    predicted: there is no model, no embedding and no fuzzy matching here.
    """
    ui.render_section(
        "Skill Gap Analyzer",
        "Pick a target role, list the skills you already have, and see exactly "
        "which of the role's requirements are still missing.",
    )

    if roles.empty or roles["role"].dropna().empty:
        ui.render_empty_state("No job roles are available to compare against.")
        return

    available = roles.dropna(subset=["role"]).copy()
    role_options = [str(role) for role in available["role"]]
    job_counts = {str(role): int(count) for role, count in zip(available["role"], available["job_count"])}
    skill_counts = {
        str(role): int(count) for role, count in zip(available["role"], available["skill_count"])
    }

    def role_label(role: str) -> str:
        """Dropdown text: the role plus how much evidence backs it."""
        postings = job_counts.get(role, 0)
        required = skill_counts.get(role, 0)
        noun = "posting" if postings == 1 else "postings"
        return f"{role} · {postings} {noun} · {required} required skills"

    left, right = st.columns([2, 3], gap="large")
    with left:
        selected_role = st.selectbox(
            "Target role",
            options=role_options,
            format_func=role_label,
            key="skill_gap_role",
            help="Every advertised job title in the database. Nothing is hardcoded.",
        )
    with right:
        user_skills = st.text_input(
            "Your current skills",
            placeholder="Python, SQL, Pandas, Git, Docker",
            key="skill_gap_skills",
            help=(
                "Separate skills with commas, semicolons, or new lines. "
                "Capitalisation does not matter, and repeats are counted once."
            ),
            icon=":material/checklist:",
        )

    st.markdown(
        '<div class="sidebar-note">'
        "Skill match % = matched required skills ÷ total required skills × 100. "
        "Names are compared after trimming, lower-casing and removing duplicates."
        "</div>",
        unsafe_allow_html=True,
    )

    if st.button(
        "Analyze Skills",
        key="skill_gap_analyze",
        type="primary",
        icon=":material/analytics:",
    ):
        # Remember which role the visible result belongs to. Changing the role
        # afterwards hides the stale result and asks for a fresh analysis;
        # editing the skill list just re-scores against the same role.
        st.session_state["skill_gap_analyzed_role"] = selected_role

    st.markdown('<div class="dash-rule"></div>', unsafe_allow_html=True)

    if st.session_state.get("skill_gap_analyzed_role") != selected_role:
        st.info(
            "Choose a target role, list your skills above, then press "
            "**Analyze Skills**.",
            icon=":material/travel_explore:",
        )
        return

    try:
        required = load_required_skills(selected_role)
    except (ConfigurationError, DatabaseConnectionError, psycopg.Error, ValueError) as exc:
        ui.render_database_error(exc)
        st.stop()

    result = ui.analyze_skill_gap(
        required_skills=required,
        user_skills=user_skills,
        catalog=catalog,
        role=selected_role,
    )
    ui.render_skill_gap_result(result)


# -----------------------------------------------------------------------------
# TAB: ROLE RECOMMENDATIONS
# -----------------------------------------------------------------------------


def tab_role_recommendations(profiles: pd.DataFrame) -> None:
    """Rank the roles in this market by how similar their required skills are.

    The ranking itself is computed by ``ml.recommender.recommend_with_diagnostics``
    - TF-IDF + cosine similarity - and this tab only draws its output. No
    machine-learning logic lives in this file: the tab picks the top five,
    explains the edge cases, and points at the rule-based Skill Gap Analyzer for
    the coverage question.
    """
    ui.render_section(
        "Role Recommendations",
        "List the skills you already have and see which roles in this market "
        "they resemble most, scored by TF-IDF similarity and shown next to the "
        "plain rule-based match.",
    )

    if profiles.empty:
        ui.render_empty_state("No role profiles are available to recommend against.")
        return

    user_skills = st.text_input(
        "Your current skills",
        placeholder="Python, SQL, Pandas, Git, Docker",
        key="recommendation_skills",
        help=(
            "Separate skills with commas, semicolons, or new lines. "
            "Capitalisation does not matter, repeats are counted once, and only "
            "skills this market knows can influence the score."
        ),
        icon=":material/checklist:",
    )

    if st.button(
        "Recommend Roles",
        key="recommendation_run",
        type="primary",
        icon=":material/route:",
    ):
        st.session_state["recommendations_requested"] = True

    st.markdown('<div class="dash-rule"></div>', unsafe_allow_html=True)

    if not st.session_state.get("recommendations_requested"):
        ui.render_recommendation_results(None, profiles)
        return

    # Scored here, in the ML layer, so the tab below draws a DataFrame it never
    # had to construct. Reruns after the first press re-score the current text.
    diag = recommend_with_diagnostics(user_skills, profiles, top_n=5)
    ui.render_recommendation_results(diag, profiles)
    ui.render_model_information(diag["info"])


# -----------------------------------------------------------------------------
# APP
# -----------------------------------------------------------------------------


def main() -> None:
    """Load the data once, render the header, sidebar and tabs."""
    ui.render_header(PAGE_TITLE, PAGE_SUBTITLE)

    try:
        jobs = load_jobs()
        links = load_job_skill_links()
        market_top_skills = load_market_top_skills()
        salary_by_role = load_salary_by_role()
        market_experience = load_experience_distribution()
        table_counts = load_table_counts()
        job_roles = load_job_roles()
        skill_catalog = load_skill_catalog()
        recommendation_profiles = load_recommendation_profiles()
    except (ConfigurationError, DatabaseConnectionError, psycopg.Error, ValueError) as exc:
        ui.render_database_error(exc)
        st.stop()

    market_jobs = 0
    if not table_counts.empty:
        counts = table_counts.set_index("table_name")["row_count"]
        market_jobs = int(counts.get("jobs", len(jobs)))

    st.session_state["selections"] = ui.render_sidebar(jobs)

    tabs = st.tabs(
        [
            "Overview",
            "Job Demand",
            "Skill Demand",
            "Salary Analytics",
            "Experience Analytics",
            "Recent Jobs",
            "Skill Gap Analyzer",
            "Role Recommendations",
        ]
    )
    with tabs[0]:
        tab_overview(jobs, links, market_jobs)
    with tabs[1]:
        tab_job_demand(jobs)
    with tabs[2]:
        tab_skill_demand(jobs, links, market_top_skills)
    with tabs[3]:
        tab_salary_analytics(jobs, salary_by_role)
    with tabs[4]:
        tab_experience(jobs, market_experience)
    with tabs[5]:
        tab_recent_jobs(jobs)
    # Appended last on purpose: the six existing tabs keep their names, their
    # order and their widget keys, so nothing that was already working shifts.
    with tabs[6]:
        tab_skill_gap(job_roles, skill_catalog)
    # The two skill tools stay next to each other and last: the rule-based
    # Skill Gap answers "do I cover this role?" and the ML tab answers
    # "which roles look like me?", so one is the natural next stop after the
    # other.
    with tabs[7]:
        tab_role_recommendations(recommendation_profiles)

    with st.sidebar:
        st.markdown('<div class="sidebar-rule"></div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="sidebar-note">Source: PostgreSQL · {len(jobs):,} postings · '
            f"{int(links['skill_id'].nunique()):,} skills · "
            f"{int(jobs['company_id'].nunique()):,} companies</div>",
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()
