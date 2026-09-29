"""Tests for the Streamlit dashboard layer.

The dashboard's own logic lives in ``dashboard/components.py`` as pure pandas
functions, so most of what is worth testing can be tested without starting a
Streamlit server. The last test uses Streamlit's own ``AppTest`` harness to run
``dashboard/app.py`` end to end and is skipped when PostgreSQL is unreachable.

Run with::

    .\\.venv\\Scripts\\Activate.ps1
    python -m pytest -v
"""

from __future__ import annotations

import pandas as pd
import pytest

from dashboard import components as ui
from src.data import queries
from src.data.database import test_connection as check_connection

# ---------------------------------------------------------------------------
# A small hand-built market, so the counting logic is tested against known
# numbers instead of whatever happens to be in the database today.
# ---------------------------------------------------------------------------

SAMPLE_JOBS = pd.DataFrame(
    {
        "job_id": [1, 2, 3, 4, 5, 6],
        "company_id": [10, 10, 20, 20, 30, 30],
        "company_name": ["Alpha", "Alpha", "Beta", "Beta", "Gamma", "Gamma"],
        "industry": ["Technology", "Technology", "Finance", "Finance", "Healthcare", "Healthcare"],
        "job_title": ["Data Analyst", "Data Engineer", "Data Analyst", "ML Engineer", "Data Analyst", "ML Engineer"],
        "location": ["Pune", "Pune", "Mumbai", "Mumbai", "Boston", "Boston"],
        "country": ["IN", "IN", "IN", "IN", "US", "US"],
        "employment_type": ["FULL_TIME", "CONTRACT", "FULL_TIME", "FULL_TIME", "PART_TIME", "FULL_TIME"],
        "work_mode": ["REMOTE", "HYBRID", "ONSITE", "REMOTE", "HYBRID", "ONSITE"],
        "experience_min": [0, 3, 2, 5, 7, 1],
        "experience_max": [2, 6, 4, 8, 9, 3],
        "salary_min": [600000.0, 1200000.0, 700000.0, 1500000.0, 90.0, 100.0],
        "salary_max": [900000.0, 1800000.0, 1000000.0, 2100000.0, 120.0, 130.0],
        "currency": ["INR", "INR", "INR", "INR", "USD", "USD"],
        "salary_period": ["YEARLY", "YEARLY", "YEARLY", "YEARLY", "HOURLY", "HOURLY"],
        "posted_date": pd.to_datetime(
            ["2026-01-05", "2026-02-10", "2026-03-15", "2026-04-20", "2026-05-25", "2026-06-30"]
        ),
    }
)

SAMPLE_LINKS = pd.DataFrame(
    {
        "job_id": [1, 1, 1, 2, 2, 2, 3, 3, 4, 4, 4, 4, 5, 5, 6, 6, 6],
        "skill_id": [1, 2, 3, 1, 2, 5, 1, 4, 1, 2, 3, 5, 1, 4, 1, 2, 3],
        "skill_name": [
            "Python", "SQL", "Linux", "Python", "SQL", "Java", "Python", "Spark",
            "Python", "SQL", "Linux", "Java", "Python", "Spark", "Python", "SQL", "Linux",
        ],
        "skill_category": [
            "Programming Language", "Database", "DevOps", "Programming Language",
            "Database", "Programming Language", "Programming Language", "Big Data",
            "Programming Language", "Database", "DevOps", "Programming Language",
            "Programming Language", "Big Data", "Programming Language", "Database", "DevOps",
        ],
    }
)


def _database_available() -> tuple[bool, str]:
    try:
        result = check_connection()
    except Exception as exc:  # any driver-level failure means "not available"
        return False, f"{type(exc).__name__}: {exc}"
    return True, f"connected to {result.get('database')}"


_DATABASE_AVAILABLE, _DATABASE_REASON = _database_available()


@pytest.fixture(scope="session")
def database() -> str:
    """Skip database-backed tests when PostgreSQL is not reachable."""
    if not _DATABASE_AVAILABLE:
        pytest.skip(
            "This test needs a running local PostgreSQL database and DB_USER / "
            "DB_PASSWORD in .env. Reason: " + _DATABASE_REASON
        )
    return _DATABASE_REASON


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def test_no_filters_returns_every_row() -> None:
    """An empty selection must mean 'everything', not 'nothing'."""
    assert len(ui.apply_filters(SAMPLE_JOBS, {})) == len(SAMPLE_JOBS)
    assert len(ui.apply_filters(SAMPLE_JOBS, {"country": [], "work_mode": []})) == len(SAMPLE_JOBS)


def test_single_filter_narrows_the_frame() -> None:
    filtered = ui.apply_filters(SAMPLE_JOBS, {"country": ["IN"]})
    assert len(filtered) == 4
    assert set(filtered["country"]) == {"IN"}


def test_filters_combine_with_and() -> None:
    filtered = ui.apply_filters(SAMPLE_JOBS, {"country": ["IN"], "work_mode": ["REMOTE"]})
    assert len(filtered) == 2
    assert set(filtered["work_mode"]) == {"REMOTE"}
    assert set(filtered["job_id"]) == {1, 4}


def test_filter_values_do_not_mix_or_leak() -> None:
    """A value belonging to another column must not match."""
    assert ui.apply_filters(SAMPLE_JOBS, {"country": ["Finance"]}).empty
    assert ui.apply_filters(SAMPLE_JOBS, {"industry": ["IN"]}).empty
    # A SQL fragment stays a literal string, so it simply matches nothing.
    assert ui.apply_filters(SAMPLE_JOBS, {"country": ["'; DROP TABLE jobs; --"]}).empty


def test_filter_labels_are_readable() -> None:
    assert ui.format_filter_value("work_mode", "FULL_TIME") == "Full Time"
    assert ui.format_filter_value("employment_type", "PART_TIME") == "Part Time"
    # Job titles keep their own capitalisation.
    assert ui.format_filter_value("job_title", "AI Engineer") == "AI Engineer"
    assert ui.format_filter_value("country", "IN") == "IN"


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------


def test_kpi_values_are_counted_from_the_data() -> None:
    cards = {card["label"]: card for card in ui.kpi_cards(SAMPLE_JOBS, SAMPLE_LINKS, 99)}
    assert cards["Total Jobs"]["value"] == "6"
    assert cards["Companies Hiring"]["value"] == "3"
    assert cards["Remote Jobs"]["value"] == "2"
    assert cards["Hybrid Jobs"]["value"] == "2"
    assert cards["Onsite Jobs"]["value"] == "2"
    assert "99" in cards["Total Jobs"]["sub"]
    assert cards["Total Skills"]["value"] == "5"


def test_kpis_follow_the_filtered_selection() -> None:
    filtered = ui.apply_filters(SAMPLE_JOBS, {"country": ["US"]})
    links = SAMPLE_LINKS[SAMPLE_LINKS["job_id"].isin(set(filtered["job_id"]))]
    cards = {card["label"]: card for card in ui.kpi_cards(filtered, links, 6)}

    assert cards["Total Jobs"]["value"] == "2"
    assert cards["Companies Hiring"]["value"] == "1"
    assert cards["Remote Jobs"]["value"] == "0"
    assert cards["Hybrid Jobs"]["value"] == "1"
    assert cards["Onsite Jobs"]["value"] == "1"


def test_kpis_survive_an_empty_selection() -> None:
    empty = SAMPLE_JOBS.iloc[0:0]
    cards = {card["label"]: card for card in ui.kpi_cards(empty, empty, 6)}
    assert cards["Total Jobs"]["value"] == "0"
    assert cards["Companies Hiring"]["value"] == "0"
    assert cards["Total Skills"]["value"] == "0"


# ---------------------------------------------------------------------------
# Skill demand
# ---------------------------------------------------------------------------


def test_skill_demand_counts_jobs_companies_and_share() -> None:
    demand = ui.build_skill_demand(SAMPLE_LINKS, SAMPLE_JOBS).set_index("skill_name")

    # Python is required by all 6 postings, from all 3 employers.
    assert demand.loc["Python", "job_count"] == 6
    assert demand.loc["Python", "company_count"] == 3
    assert demand.loc["Python", "pct_of_jobs"] == 100.0
    # SQL covers jobs 1, 2, 4 and 6.
    assert demand.loc["SQL", "job_count"] == 4
    assert demand.loc["SQL", "pct_of_jobs"] == pytest.approx(66.67, abs=0.01)
    # Java covers only Alpha and Beta.
    assert demand.loc["Java", "job_count"] == 2
    assert demand.loc["Java", "company_count"] == 2
    assert demand.loc["Java", "pct_of_jobs"] == pytest.approx(33.33, abs=0.01)


def test_skill_demand_is_ranked_by_demand() -> None:
    demand = ui.build_skill_demand(SAMPLE_LINKS, SAMPLE_JOBS)
    counts = demand["job_count"].tolist()
    assert counts == sorted(counts, reverse=True)
    assert demand.iloc[0]["skill_name"] == "Python"


def test_skill_demand_respects_the_filtered_selection() -> None:
    filtered = ui.apply_filters(SAMPLE_JOBS, {"country": ["US"]})
    demand = ui.build_skill_demand(SAMPLE_LINKS, filtered)
    assert set(demand["skill_name"]) == {"Python", "SQL", "Linux", "Spark"}
    assert demand["pct_of_jobs"].max() == 100.0


def test_skill_demand_handles_no_matches() -> None:
    empty = SAMPLE_JOBS.iloc[0:0]
    demand = ui.build_skill_demand(SAMPLE_LINKS, empty)
    assert demand.empty
    assert list(demand.columns) == [
        "skill_name", "skill_category", "job_count", "company_count", "pct_of_jobs"
    ]


def test_skills_by_category_sums_to_one_hundred_percent() -> None:
    by_category = ui.build_skills_by_category(ui.build_skill_demand(SAMPLE_LINKS, SAMPLE_JOBS))
    assert by_category["pct_of_demand"].sum() == pytest.approx(100.0)
    # Python (6 postings) + Java (2 postings) is the biggest category.
    assert by_category.iloc[0]["skill_category"] == "Programming Language"
    assert by_category.iloc[0]["skill_count"] == 2
    assert by_category.iloc[0]["job_requirements"] == 8


# ---------------------------------------------------------------------------
# Experience bands
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("years", "band"),
    [
        (0, "ENTRY (0 years)"),
        (1, "JUNIOR (1-2 years)"),
        (2, "JUNIOR (1-2 years)"),
        (3, "MID (3-5 years)"),
        (5, "MID (3-5 years)"),
        (6, "SENIOR (6-8 years)"),
        (8, "SENIOR (6-8 years)"),
        (9, "STAFF / PRINCIPAL (9+ years)"),
        (15, "STAFF / PRINCIPAL (9+ years)"),
        (None, "NOT SPECIFIED"),
        (float("nan"), "NOT SPECIFIED"),
    ],
)
def test_experience_band_thresholds(years, band) -> None:
    assert ui.experience_band(years) == band


def test_experience_distribution_keeps_all_bands_in_order() -> None:
    distribution = ui.experience_distribution(SAMPLE_JOBS)
    assert distribution["seniority_band"].tolist() == ui.EXPERIENCE_BAND_ORDER
    # experience_min values are 0, 3, 2, 5, 7, 1 -> one entry, two junior,
    # two mid, one senior, and no staff-level or undisclosed posting.
    assert distribution["jobs_posted"].tolist() == [1, 2, 2, 1, 0, 0]
    assert distribution["pct_of_all_jobs"].sum() == pytest.approx(100.0)


def test_experience_distribution_agrees_with_the_sql() -> None:
    """The pandas banding must reproduce database/queries/05 query 13 exactly."""
    market = ui.experience_distribution(queries.get_all_jobs())
    from_sql = queries.get_experience_distribution()

    merged = market.merge(from_sql, on="seniority_band", suffixes=("_pandas", "_sql"))
    assert len(merged) == len(from_sql)
    assert merged["jobs_posted_pandas"].tolist() == merged["jobs_posted_sql"].tolist()
    assert merged["companies_hiring_pandas"].tolist() == merged["companies_hiring_sql"].tolist()


# ---------------------------------------------------------------------------
# Salary: currencies and periods must stay separate
# ---------------------------------------------------------------------------


def test_salary_units_are_currency_and_period_pairs() -> None:
    assert ui.salary_units(SAMPLE_JOBS) == [("INR", "YEARLY"), ("USD", "HOURLY")]
    assert ui.unit_label(("INR", "YEARLY")) == "INR · YEARLY"


def test_salary_units_ignore_undisclosed_salary() -> None:
    undisclosed = SAMPLE_JOBS.copy()
    undisclosed["salary_min"] = float("nan")
    assert ui.salary_units(undisclosed) == []


def test_salary_by_role_matches_the_sql_aggregate(database: str) -> None:
    """The filtered pandas aggregate must reproduce get_average_salary_by_role().

    The Salary tab charts the selection and falls back to the SQL aggregate for
    the market reference, so the two must agree when nothing is filtered out -
    otherwise the same number would appear twice with two different values.
    """
    from_sql = queries.get_average_salary_by_role()
    from_pandas = ui.build_salary_by_role(queries.get_all_jobs())

    assert list(from_pandas.columns) == list(from_sql.columns)
    assert set(from_pandas["role"]) == set(from_sql["role"])

    key = ["role", "currency", "salary_period"]
    left = from_sql.set_index(key).sort_index()
    right = from_pandas.set_index(key).sort_index()
    assert list(left.index) == list(right.index)

    for column in left.columns:
        for position in range(len(left)):
            assert left[column].iloc[position] == pytest.approx(
                right[column].iloc[position], rel=1e-6
            ), f"{column} differs for {left.index[position]}"


def test_salary_by_role_only_contains_roles_in_the_selection() -> None:
    """Filtering must not leave a role in the charts that has no posting left."""
    filtered = ui.apply_filters(SAMPLE_JOBS, {"country": ["US"]})
    scoped = ui.build_salary_by_role(filtered)
    assert set(scoped["role"]) <= set(filtered["job_title"])
    assert set(scoped["role"]) == {"Data Analyst", "ML Engineer"}
    # Both US postings are USD hourly, so no other unit may appear.
    assert set(zip(scoped["currency"], scoped["salary_period"])) == {("USD", "HOURLY")}


def test_salary_by_role_excludes_undisclosed_salary() -> None:
    hidden = SAMPLE_JOBS.copy()
    hidden.loc[hidden["job_title"] == "Data Analyst", ["salary_min", "salary_max"]] = None
    scoped = ui.build_salary_by_role(hidden)
    # All three Data Analyst postings lose their salary, so only the Data
    # Engineer (INR) and the two ML Engineer postings (INR, USD) remain.
    assert set(scoped["role"]) == {"Data Engineer", "ML Engineer"}
    assert scoped["jobs_with_salary"].tolist() == [1, 1, 1]
    assert scoped["jobs_with_salary"].sum() == 3


def test_salary_by_role_is_empty_for_an_empty_selection() -> None:
    scoped = ui.build_salary_by_role(SAMPLE_JOBS.iloc[0:0])
    assert scoped.empty
    assert list(scoped.columns) == list(ui.SALARY_BY_ROLE_COLUMNS)


def test_salary_charts_never_mix_currencies() -> None:
    """A chart built for one unit must contain only that unit's roles."""
    salary_by_role = pd.DataFrame(
        {
            "role": ["Data Analyst", "Data Analyst", "ML Engineer"],
            "currency": ["INR", "USD", "INR"],
            "salary_period": ["YEARLY", "YEARLY", "YEARLY"],
            "jobs_with_salary": [2, 1, 1],
            "company_count": [2, 1, 1],
            "avg_salary_min": [600000.0, 80000.0, 1500000.0],
            "avg_salary_max": [900000.0, 100000.0, 2100000.0],
            "avg_salary_midpoint": [750000.0, 90000.0, 1800000.0],
            "lowest_salary_min": [600000.0, 80000.0, 1500000.0],
            "highest_salary_max": [900000.0, 100000.0, 2100000.0],
        }
    )
    figure = ui.chart_salary_range_by_role(salary_by_role, ("INR", "YEARLY"))
    plotted_roles = set(figure.data[0].y)
    assert plotted_roles == {"Data Analyst", "ML Engineer"}
    assert "USD" not in {str(value) for value in figure.data[0].y}

    # A unit that is not present yields a placeholder, never another currency.
    missing = ui.chart_salary_range_by_role(salary_by_role, ("EUR", "DAILY"))
    assert not missing.data


def test_salary_split_chart_counts_postings_not_amounts() -> None:
    """The cross-currency chart may list currencies, but only as counts."""
    figure = ui.chart_salary_market_split(SAMPLE_JOBS)
    units = {str(value) for value in figure.data[0].y}
    assert units == {"INR · YEARLY", "USD · HOURLY"}
    assert sum(figure.data[0].x) == len(SAMPLE_JOBS)


# ---------------------------------------------------------------------------
# Recent jobs table
# ---------------------------------------------------------------------------


def test_recent_jobs_columns_and_order() -> None:
    table = ui.build_recent_jobs(SAMPLE_JOBS)
    assert list(table.columns) == [
        "Job Title", "Company", "Industry", "Location", "Country", "Work Mode",
        "Employment Type", "Experience", "Salary", "Currency", "Salary Period",
        "Posted Date",
    ]
    # Newest first.
    assert table["Job Title"].tolist() == [
        "ML Engineer", "Data Analyst", "ML Engineer", "Data Analyst",
        "Data Engineer", "Data Analyst",
    ]
    assert pd.to_datetime(table["Posted Date"]).is_monotonic_decreasing


def test_recent_jobs_keeps_currency_and_period_separate() -> None:
    table = ui.build_recent_jobs(SAMPLE_JOBS)
    hourly_rows = table[table["Currency"] == "USD"]
    assert len(hourly_rows) == 2
    assert set(hourly_rows["Salary Period"]) == {"HOURLY"}
    # The hourly postings keep their own small amounts, not yearly-sized ones.
    assert set(hourly_rows["Salary"]) == {"90 – 120", "100 – 130"}
    yearly_rows = table[table["Currency"] == "INR"]
    assert set(yearly_rows["Salary Period"]) == {"YEARLY"}


def test_recent_jobs_formats_codes_and_ranges() -> None:
    table = ui.build_recent_jobs(SAMPLE_JOBS)
    assert set(table["Work Mode"]) == {"Remote", "Hybrid", "Onsite"}
    assert "Full Time" in set(table["Employment Type"])
    assert "0 – 2 yrs" in set(table["Experience"])


def test_salary_and_experience_formatting() -> None:
    assert ui.format_salary_text(600000, 900000) == "600,000 – 900,000"
    assert ui.format_salary_text(float("nan"), float("nan")) == "Not disclosed"
    assert ui.format_salary_text(80000, float("nan")) == "From 80,000"
    assert ui.experience_text(3, 6) == "3 – 6 yrs"
    assert ui.experience_text(3, float("nan")) == "3+ yrs"
    assert ui.experience_text(float("nan"), float("nan")) == "Not specified"


# ---------------------------------------------------------------------------
# Security and trend helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "password=hunter2",
        "PASSWORD: hunter2",
        "db_password = hunter2",
        "token=abc123",
        "secret: s3cr3t",
    ],
)
def test_redact_removes_credentials(text: str) -> None:
    cleaned = ui.redact(text)
    assert "hunter2" not in cleaned
    assert "abc123" not in cleaned
    assert "s3cr3t" not in cleaned


def test_monthly_postings_counts_once_per_job() -> None:
    monthly = ui.monthly_postings(SAMPLE_JOBS)
    assert monthly["job_count"].sum() == len(SAMPLE_JOBS)
    assert monthly["month"].is_monotonic_increasing


def test_dashboard_does_not_import_connection_helpers() -> None:
    """The dashboard must reuse the data layer, not rebuild connections."""
    from pathlib import Path

    app_source = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"
    text = app_source.read_text(encoding="utf-8")
    assert "from src.data import queries" in text
    assert "get_connection" not in text
    assert "psycopg.connect" not in text
    # Caching must be applied to data retrieval, never to a connection.
    assert "@st.cache_data" in text
    assert "@st.cache_resource" not in text


# ---------------------------------------------------------------------------
# End-to-end: run the real app through Streamlit's test harness
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("database")
def test_app_runs_end_to_end_without_exceptions(database: str) -> None:
    """dashboard/app.py renders, and its KPIs match PostgreSQL."""
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    app_path = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=180)
    app.run()

    assert not app.exception, [f"{e.type}: {e.message}" for e in app.exception]
    assert len(app.tabs) == 8
    # The six original tabs keep their names and their order; the two skill
    # tools are appended after them.
    assert [tab.label for tab in app.tabs] == [
        "Overview",
        "Job Demand",
        "Skill Demand",
        "Salary Analytics",
        "Experience Analytics",
        "Recent Jobs",
        "Skill Gap Analyzer",
        "Role Recommendations",
    ]
    assert len(app.sidebar.multiselect) == 5
    assert [button.label for button in app.sidebar.button] == ["Reset Filters"]
    assert len(app.get("plotly_chart")) >= 12

    jobs = queries.get_all_jobs()
    cards = "\n".join(block.value for block in app.markdown if "kpi-card" in block.value)
    assert f'kpi-value">{len(jobs):,}<' in cards
    assert f'kpi-value">{int(jobs["company_id"].nunique()):,}<' in cards


@pytest.mark.usefixtures("database")
def test_app_filters_change_the_kpis(database: str) -> None:
    """A sidebar filter must reach the KPI cards, and Reset must undo it."""
    import re
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    app_path = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=180)
    app.run()

    app.sidebar.multiselect[0].select("IN")
    app.run()
    assert not app.exception, [f"{e.type}: {e.message}" for e in app.exception]

    cards = "\n".join(block.value for block in app.markdown if "kpi-card" in block.value)
    shown = re.findall(r'kpi-value">([^<]+)<', cards)
    expected = int((queries.get_all_jobs()["country"] == "IN").sum())
    assert shown[0] == f"{expected:,}"

    app.sidebar.button[0].click().run()
    assert not app.exception
    cards = "\n".join(block.value for block in app.markdown if "kpi-card" in block.value)
    assert re.findall(r'kpi-value">([^<]+)<', cards)[0] == f"{len(queries.get_all_jobs()):,}"


@pytest.mark.usefixtures("database")
def test_role_recommendations_tab_renders_ranked_cards(database: str) -> None:
    """The Role Recommendations tab ranks roles and shows all five fields.

    The ranking is deterministic and computed locally by the ML layer; this
    test drives the widget, presses the button, and checks the rendered cards,
    so the wiring between the tab and the recommender is what is exercised.
    """
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    app_path = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=180)
    app.run()

    # Before any analysis: an invitation to enter skills, nothing else. The
    # CSS <style> block also mentions "rec-card", so match the rendered HTML
    # class attribute rather than the class name.
    assert not app.exception, [f"{e.type}: {e.message}" for e in app.exception]
    assert 'class="rec-card"' not in "\n".join(b.value for b in app.markdown)

    app.text_input(key="recommendation_skills").set_value("Python, SQL, Pandas, Git, Docker")
    app.button(key="recommendation_run").click().run()
    assert not app.exception, [f"{e.type}: {e.message}" for e in app.exception]

    cards = "\n".join(block.value for block in app.markdown if "rec-card" in block.value)
    assert cards.count('class="rec-card"') == 5
    assert "Rank #1" in cards
    assert "Skill Similarity Score" in cards
    assert "%" in cards
    assert "You have (" in cards
    assert "Missing (" in cards
    assert "Required:" in cards
    # Every card must show matched _and_ missing badges.
    assert "skill-badge--matched" in cards
    assert "skill-badge--missing" in cards

    # No ML vocabulary leaks into the dashboard: the cards describe outcome,
    # and the model panel stays in an expander.
    assert "tf-idf" not in cards.lower()


@pytest.mark.usefixtures("database")
def test_role_recommendations_tab_explains_empty_and_unknown_input(database: str) -> None:
    """Empty and wholly-unknown skill lists get an explanation, not a crash."""
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    app_path = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=180)
    app.run()

    app.text_input(key="recommendation_skills").set_value("   ,  ")
    app.button(key="recommendation_run").click().run()
    assert not app.exception, [f"{e.type}: {e.message}" for e in app.exception]
    info = "\n".join(getattr(block, "value", "") for block in app.info)
    assert "Please enter at least one skill." in info
    assert 'class="rec-card"' not in "\n".join(b.value for b in app.markdown)

    app.text_input(key="recommendation_skills").set_value("COBOL, Quantum Computing")
    app.button(key="recommendation_run").click().run()
    assert not app.exception, [f"{e.type}: {e.message}" for e in app.exception]
    warning = "\n".join(getattr(block, "value", "") for block in app.warning)
    assert "vocabulary" in warning
    assert 'class="rec-card"' not in "\n".join(b.value for b in app.markdown)
