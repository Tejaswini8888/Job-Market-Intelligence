r"""Tests for the Skill Gap Analyzer.

Two kinds of test live here, and they are deliberately kept apart:

* **Pure logic** - normalization, duplicate removal, case-insensitive matching
  and the percentage calculation. These run against small, hand-written frames
  whose answers are known by hand, so they never depend on what the database
  happens to contain today.
* **Database-backed** - required skills really coming out of PostgreSQL, and
  proof that the role name is bound as a parameter rather than pasted into SQL.

No test here contains a password. Every connection setting comes from the
environment (``.env`` / ``DB_*`` variables), and one test explicitly asserts
that the real password does not appear anywhere in the feature's source.

Run with::

    .\.venv\Scripts\Activate.ps1
    python -m pytest -v
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

import pandas as pd
import pytest

from dashboard import components as ui
from src.data import queries
from src.data.database import get_database_config, test_connection as check_connection

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Synthetic data for the pure-logic tests.
#
# REQUIRED_SKILLS is the worked example from the feature specification:
# five required skills, of which the candidate holds three.
# ---------------------------------------------------------------------------

REQUIRED_SKILLS = pd.DataFrame(
    {
        "skill_id": [1, 4, 10, 20, 12],
        "skill_name": ["Python", "SQL", "Docker", "PyTorch", "Git"],
        "skill_category": [
            "Programming Language",
            "Programming Language",
            "DevOps",
            "Machine Learning",
            "Tools",
        ],
        "job_count": [4, 4, 3, 2, 2],
        "pct_of_role_jobs": [100.0, 100.0, 75.0, 50.0, 50.0],
    }
)

#: Everything the fake market above knows about, so "not required for this
#: role" can be told apart from "not in the database at all".
SKILL_CATALOG = pd.DataFrame(
    {
        "skill_id": [1, 3, 4, 10, 12, 16, 20, 19, 5],
        "skill_name": [
            "Python",
            "Java",
            "SQL",
            "Docker",
            "Git",
            "Pandas",
            "PyTorch",
            "TensorFlow",
            "C++",
        ],
        "skill_category": [
            "Programming Language",
            "Programming Language",
            "Programming Language",
            "DevOps",
            "Tools",
            "Data Science",
            "Machine Learning",
            "Machine Learning",
            "Programming Language",
        ],
    }
)


# ---------------------------------------------------------------------------
# Database fixture - the same pattern the other two test modules use. Database
# tests are SKIPPED with a reason when PostgreSQL is unreachable, so the pure
# logic above still runs on a machine with no database.
# ---------------------------------------------------------------------------


def _database_available() -> tuple[bool, str]:
    try:
        result = check_connection()
    except Exception as exc:  # any driver-level failure means "not available"
        return False, f"{type(exc).__name__}: {exc}"
    return True, f"connected to {result.get('database')}"


_DATABASE_AVAILABLE, _DATABASE_REASON = _database_available()


@pytest.fixture(scope="session")
def database() -> str:
    """Skip the test unless the local PostgreSQL database is reachable."""
    if not _DATABASE_AVAILABLE:
        pytest.skip(
            "This test needs a running local PostgreSQL database and DB_USER / "
            "DB_PASSWORD in .env. Reason: " + _DATABASE_REASON
        )
    return _DATABASE_REASON


# ---------------------------------------------------------------------------
# 1. Skill normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("python", "python"),
        ("  Python  ", "python"),
        ("PYTHON", "python"),
        ("PyTorch", "pytorch"),
        ("Natural   Language Processing", "natural language processing"),
        ("Deep Learning\n", "deep learning"),
        ("C++", "c++"),
    ],
)
def test_normalize_skill_name_trims_lowercases_and_collapses(raw: str, expected: str) -> None:
    """Whitespace and case must never decide whether a skill matches."""
    assert ui.normalize_skill_name(raw) == expected


def test_normalize_skill_name_rejects_non_strings() -> None:
    with pytest.raises(TypeError):
        ui.normalize_skill_name(42)  # type: ignore[arg-type]


def test_parse_user_skills_splits_on_every_documented_separator() -> None:
    """A comma list is the documented format; the others are just tolerated."""
    assert ui.parse_user_skills("Python, SQL, Pandas") == ["Python", "SQL", "Pandas"]
    assert ui.parse_user_skills("Python; SQL | Pandas") == ["Python", "SQL", "Pandas"]
    assert ui.parse_user_skills("Python\nSQL\r\nPandas") == ["Python", "SQL", "Pandas"]


def test_parse_user_skills_drops_blanks_and_collapses_spacing() -> None:
    """A trailing comma or a double space is not an error."""
    assert ui.parse_user_skills("  Python ,,  SQL ,  ") == ["Python", "SQL"]
    assert ui.parse_user_skills("Deep   Learning") == ["Deep Learning"]
    assert ui.parse_user_skills("") == []
    assert ui.parse_user_skills("   ") == []
    assert ui.parse_user_skills(None) == []


def test_parse_user_skills_does_not_split_names_that_contain_symbols() -> None:
    """/" and "+" appear inside real skill names, so they are not separators."""
    assert ui.parse_user_skills("CI/CD, C++") == ["CI/CD", "C++"]


# ---------------------------------------------------------------------------
# 2. Duplicate removal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "Python, Python, Python",
        "Python, python, PYTHON, PyThOn",
        "  Python ,  python  ",
        "Python;Python|Python",
    ],
)
def test_duplicate_user_skills_are_counted_once(raw: str) -> None:
    """A skill typed three times is still one skill, however it is capitalised."""
    assert ui.parse_user_skills(raw) == ["Python"]


def test_duplicates_do_not_change_the_percentage() -> None:
    """Repeating a skill must not inflate or deflate the score."""
    once = ui.analyze_skill_gap(REQUIRED_SKILLS, "Python, SQL, Git", SKILL_CATALOG)
    thrice = ui.analyze_skill_gap(
        REQUIRED_SKILLS, "Python, Python, SQL, sql, Git, GIT, Git", SKILL_CATALOG
    )
    assert thrice.skill_match_pct == once.skill_match_pct
    assert thrice.matched_count == once.matched_count
    assert thrice.user_skills == once.user_skills


def test_duplicate_required_skills_are_counted_once() -> None:
    """A repeated requirement row must not inflate the denominator."""
    doubled = pd.concat([REQUIRED_SKILLS, REQUIRED_SKILLS], ignore_index=True)
    result = ui.analyze_skill_gap(doubled, "Python", SKILL_CATALOG)
    assert result.required_count == 5
    assert result.skill_match_pct == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# 3. Case-insensitive matching
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "typed",
    [
        "python, sql, git",
        "PYTHON, SQL, GIT",
        "PyThOn, SqL, gIt",
    ],
)
def test_matching_ignores_case(typed: str) -> None:
    """Python = python = PYTHON, exactly as the feature requires."""
    result = ui.analyze_skill_gap(REQUIRED_SKILLS, typed, SKILL_CATALOG)
    assert result.matched_count == 3
    assert result.skill_match_pct == pytest.approx(60.0)
    assert set(result.matched["skill_name"]) == {"Python", "SQL", "Git"}


def test_matching_ignores_surrounding_and_internal_whitespace() -> None:
    result = ui.analyze_skill_gap(
        REQUIRED_SKILLS, "  python ,  PyTorch  , docker ", SKILL_CATALOG
    )
    assert set(result.matched["skill_name"]) == {"Python", "PyTorch", "Docker"}
    assert result.skill_match_pct == pytest.approx(60.0)


def test_similar_but_different_skills_do_not_match_each_other() -> None:
    """PyTorch must not satisfy a TensorFlow requirement - no synonym logic."""
    result = ui.analyze_skill_gap(REQUIRED_SKILLS, "TensorFlow", SKILL_CATALOG)
    assert result.matched_count == 0
    assert "TensorFlow" in result.recognized_not_required
    assert result.skill_match_pct == 0.0

    # The reverse direction too: neither framework is treated as the other.
    frameworks = pd.DataFrame({"skill_name": ["TensorFlow"]})
    assert ui.analyze_skill_gap(frameworks, "PyTorch", SKILL_CATALOG).matched_count == 0
    # ... and a genuine prefix ("Git" vs "GitHub Actions") is not a match either.
    assert ui.analyze_skill_gap(frameworks, "Tens", SKILL_CATALOG).matched_count == 0


# ---------------------------------------------------------------------------
# 4. Percentage calculation - the transparent rule
# ---------------------------------------------------------------------------


def test_percentage_is_matched_over_required() -> None:
    """matched required skills / total required skills * 100, from the spec."""
    result = ui.analyze_skill_gap(REQUIRED_SKILLS, "Python, SQL, Git", SKILL_CATALOG)

    assert result.required_count == 5
    assert result.matched_count == 3
    assert result.skill_match_pct == pytest.approx(3 / 5 * 100)
    assert result.skill_match_text == "60%"


@pytest.mark.parametrize(
    ("typed", "expected_pct", "expected_text"),
    [
        ("Python, SQL, Git, Docker, PyTorch", 100.0, "100%"),
        ("Python, SQL, Git", 60.0, "60%"),
        ("Python, SQL", 40.0, "40%"),
        ("Git", 20.0, "20%"),
        ("Java", 0.0, "0%"),
    ],
)
def test_percentage_values(typed: str, expected_pct: float, expected_text: str) -> None:
    result = ui.analyze_skill_gap(REQUIRED_SKILLS, typed, SKILL_CATALOG)
    assert result.skill_match_pct == pytest.approx(expected_pct)
    assert result.skill_match_text == expected_text


def test_percentage_keeps_one_decimal_when_it_does_not_divide_evenly() -> None:
    """1 of 3 is 33.33...% - shown as 33.3%, never rounded to 33% or 34%."""
    three = pd.DataFrame({"skill_name": ["Python", "SQL", "Git"]})
    result = ui.analyze_skill_gap(three, "Python", SKILL_CATALOG)

    assert result.skill_match_pct == pytest.approx(100 / 3)
    assert result.skill_match_text == "33.3%"


def test_matched_and_missing_partition_the_required_skills() -> None:
    """The two lists together are exactly the requirement set, with no overlap."""
    result = ui.analyze_skill_gap(REQUIRED_SKILLS, "python, sql, pandas", SKILL_CATALOG)

    assert result.matched_count + result.missing_count == result.required_count
    assert not set(result.matched["skill_name"]) & set(result.missing["skill_name"])
    assert set(result.matched["skill_name"]) | set(result.missing["skill_name"]) == set(
        REQUIRED_SKILLS["skill_name"]
    )


def test_matched_and_missing_keep_the_database_ordering() -> None:
    """Skills stay ranked by how widely the role asks for them."""
    result = ui.analyze_skill_gap(REQUIRED_SKILLS, "Git, Python, Java", SKILL_CATALOG)
    # Database order is Python, SQL, Docker, PyTorch, Git.
    assert list(result.matched["skill_name"]) == ["Python", "Git"]
    assert list(result.missing["skill_name"]) == ["SQL", "Docker", "PyTorch"]


def test_percentage_is_unaffected_by_skills_the_role_does_not_require() -> None:
    """Extra skills can never inflate the score."""
    without_extras = ui.analyze_skill_gap(REQUIRED_SKILLS, "Python, SQL, Git", SKILL_CATALOG)
    with_extras = ui.analyze_skill_gap(
        REQUIRED_SKILLS, "Python, SQL, Git, Pandas, Java", SKILL_CATALOG
    )
    assert with_extras.skill_match_pct == without_extras.skill_match_pct == pytest.approx(60.0)
    assert set(with_extras.recognized_not_required) == {"Java", "Pandas"}


# ---------------------------------------------------------------------------
# 5. Empty input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["", "   ", "\n", ",", " , , "])
def test_empty_skill_input_produces_no_matches_and_no_crash(raw: str) -> None:
    """Empty input is a state the UI explains, not an exception."""
    result = ui.analyze_skill_gap(REQUIRED_SKILLS, raw, SKILL_CATALOG)

    assert result.has_user_skills is False
    assert result.matched_count == 0
    assert result.skill_match_pct == 0.0
    assert result.skill_match_text == "0%"
    # Every requirement is still listed, so the user can see what to type.
    assert result.missing_count == result.required_count == 5
    assert result.unrecognized == ()


def test_empty_input_says_what_to_do() -> None:
    """The wording shown to the user is part of the feature contract."""
    result = ui.analyze_skill_gap(REQUIRED_SKILLS, "", SKILL_CATALOG)
    assert "enter your skills" in ui.skill_gap_summary_sentence(result).lower()


def test_analysis_still_works_with_no_user_skills_at_all() -> None:
    """The function is total: required=None and empty input is a valid call."""
    result = ui.analyze_skill_gap(None, "", SKILL_CATALOG, role="Anything")
    assert result.has_required_skills is False
    assert result.has_user_skills is False
    assert result.skill_match_pct == 0.0
    assert result.role == "Anything"


# ---------------------------------------------------------------------------
# 6. Unknown skills
# ---------------------------------------------------------------------------


def test_unknown_skill_is_reported_but_does_not_break_the_analysis() -> None:
    """A name the database has never seen is ignored, not fatal."""
    result = ui.analyze_skill_gap(
        REQUIRED_SKILLS, "Python, SQL, Git, QuantumFlux", SKILL_CATALOG
    )

    assert result.has_unknown_skills is True
    assert result.unrecognized == ("QuantumFlux",)
    # The recognised skills are still analysed, at full value.
    assert result.matched_count == 3
    assert result.skill_match_pct == pytest.approx(60.0)
    # An unknown skill is never a match, whatever else is true.
    assert "QuantumFlux" not in set(result.matched["skill_name"])


def test_all_skills_unknown_gives_a_zero_match() -> None:
    result = ui.analyze_skill_gap(REQUIRED_SKILLS, "Aaa, Bbb, Ccc", SKILL_CATALOG)
    assert result.unrecognized == ("Aaa", "Bbb", "Ccc")
    assert result.skill_match_pct == 0.0
    assert result.missing_count == 5


def test_unknown_skill_never_counts_towards_the_denominator() -> None:
    """Typing 50 unknown skills must not change the score at all."""
    junk = ", ".join(f"Unknown{i}" for i in range(50))
    result = ui.analyze_skill_gap(REQUIRED_SKILLS, junk, SKILL_CATALOG)
    assert result.required_count == 5
    assert result.skill_match_pct == 0.0


def test_known_but_not_required_is_not_reported_as_unknown() -> None:
    """Pandas exists in the market, it is simply not an ML Engineer skill."""
    result = ui.analyze_skill_gap(REQUIRED_SKILLS, "Pandas, Java", SKILL_CATALOG)
    assert result.has_unknown_skills is False
    assert set(result.recognized_not_required) == {"Pandas", "Java"}


def test_not_required_skills_use_the_database_spelling() -> None:
    """The report shows the canonical name, so it can be searched for later."""
    result = ui.analyze_skill_gap(REQUIRED_SKILLS, "pandas, JAVA", SKILL_CATALOG)
    assert result.recognized_not_required == ("Pandas", "Java")


def test_without_a_catalog_nothing_is_claimed_to_be_unknown() -> None:
    """Unknownness is unverifiable without the catalog, so it is not asserted."""
    result = ui.analyze_skill_gap(REQUIRED_SKILLS, "Python, zzz", None)
    assert result.matched_count == 1
    assert result.unrecognized == ()
    assert set(result.recognized_not_required) == {"zzz"}

    # A catalog with no skill_name column is equally unusable, and must not be
    # mistaken for "none of these skills exist".
    empty_catalog = pd.DataFrame({"skill_id": [1, 2]})
    result = ui.analyze_skill_gap(REQUIRED_SKILLS, "Python, zzz", empty_catalog)
    assert result.unrecognized == ()
    assert set(result.recognized_not_required) == {"zzz"}


# ---------------------------------------------------------------------------
# 7. No matched skills
# ---------------------------------------------------------------------------


def test_no_overlap_reports_zero_and_lists_everything_as_missing() -> None:
    result = ui.analyze_skill_gap(REQUIRED_SKILLS, "Java, C#, Ruby", SKILL_CATALOG)

    assert result.matched_count == 0
    assert result.skill_match_pct == 0.0
    assert result.skill_match_text == "0%"
    assert list(result.missing["skill_name"]) == list(REQUIRED_SKILLS["skill_name"])
    assert result.missing_count == 5
    assert result.matched.empty


def test_no_overlap_summary_reports_zero_percent_skill_match() -> None:
    result = ui.analyze_skill_gap(REQUIRED_SKILLS, "Java", SKILL_CATALOG)
    assert "0% skill match" in ui.skill_gap_summary_sentence(result)


# ---------------------------------------------------------------------------
# 8. Full match
# ---------------------------------------------------------------------------


def test_full_match_is_one_hundred_percent_with_nothing_missing() -> None:
    result = ui.analyze_skill_gap(
        REQUIRED_SKILLS, "Python, SQL, Docker, PyTorch, Git", SKILL_CATALOG
    )

    assert result.matched_count == result.required_count == 5
    assert result.missing_count == 0
    assert result.missing.empty
    assert result.skill_match_pct == 100.0
    assert result.skill_match_text == "100%"


def test_full_match_survives_odd_spelling_and_duplicates() -> None:
    result = ui.analyze_skill_gap(
        REQUIRED_SKILLS,
        " python ,SQL,  docker ,pytorch, Git, git, PYTORCH ",
        SKILL_CATALOG,
    )
    assert result.skill_match_pct == 100.0
    assert result.missing_count == 0


def test_full_match_is_robust_to_extra_skills() -> None:
    result = ui.analyze_skill_gap(
        REQUIRED_SKILLS,
        "Python, SQL, Docker, PyTorch, Git, Pandas, Java, Git, C++",
        SKILL_CATALOG,
    )
    assert result.skill_match_pct == 100.0
    assert set(result.recognized_not_required) == {"Pandas", "Java", "C++"}


# ---------------------------------------------------------------------------
# Role with no skills, and the result object as a whole
# ---------------------------------------------------------------------------


def test_role_with_no_skills_is_reported_clearly() -> None:
    """A role nothing was recorded for must not show a misleading 0% match."""
    result = ui.analyze_skill_gap(pd.DataFrame(columns=["skill_name"]), "Python, SQL", SKILL_CATALOG)

    assert result.has_required_skills is False
    assert result.required_count == 0
    assert result.skill_match_pct == 0.0
    assert result.matched.empty
    assert result.missing.empty
    assert "no recorded skill requirements" in ui.skill_gap_summary_sentence(result)


def test_required_skills_may_arrive_as_a_single_column() -> None:
    """The analyser accepts the leanest possible frame without extra work."""
    result = ui.analyze_skill_gap(pd.DataFrame({"skill_name": ["Python", "SQL"]}), "Python")
    assert result.required_count == 2
    assert result.skill_match_pct == pytest.approx(50.0)
    assert set(result.required.columns) == set(ui.SKILL_GAP_COLUMNS)
    # Absent metadata is filled, never left as NaN or None.
    assert result.required["skill_category"].tolist() == [ui.UNCATEGORISED, ui.UNCATEGORISED]
    assert result.required["job_count"].tolist() == [0, 0]
    assert result.required["pct_of_role_jobs"].tolist() == [0.0, 0.0]


def test_a_frame_without_a_skill_name_column_is_rejected() -> None:
    with pytest.raises(ValueError):
        ui.analyze_skill_gap(pd.DataFrame({"name": ["Python"]}), "Python")


def test_result_exposes_counts_used_by_the_cards() -> None:
    result = ui.analyze_skill_gap(REQUIRED_SKILLS, "Python, SQL, Git", SKILL_CATALOG)
    cards = {card["label"]: card for card in ui.skill_gap_kpi_cards(result)}

    assert cards["Matched Skills"]["value"] == "3"
    assert cards["Missing Skills"]["value"] == "2"
    assert cards["Required Skills"]["value"] == "5"
    # Every card carries the accent colour the renderer needs.
    assert all(card["accent"].startswith("#") for card in cards.values())


# ---------------------------------------------------------------------------
# 9. Required skills retrieved from the real database
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("database")
def test_available_job_roles_come_from_the_jobs_table(database: str) -> None:
    """The role dropdown is built from the database, never from a hardcoded list."""
    roles = queries.get_available_job_roles()

    assert isinstance(roles, pd.DataFrame)
    assert list(roles.columns) == ["role", "job_count", "company_count", "skill_count"]
    assert not roles.empty

    titles = set(queries.get_all_jobs()["job_title"])
    assert set(roles["role"]) == titles
    assert roles["job_count"].sum() == len(queries.get_all_jobs())
    assert (roles["job_count"] > 0).all()
    assert (roles["skill_count"] > 0).all()


@pytest.mark.usefixtures("database")
def test_required_skills_for_role_come_from_the_database(database: str) -> None:
    """Every required skill must be a real skill attached to a real posting."""
    role = str(queries.get_job_counts_by_role().iloc[0]["role"])
    required = queries.get_required_skills_for_role(role)

    assert isinstance(required, pd.DataFrame)
    assert list(required.columns) == [
        "skill_id",
        "skill_name",
        "skill_category",
        "job_count",
        "company_count",
        "pct_of_role_jobs",
    ]
    assert not required.empty
    # One row per DISTINCT skill, never one per (job, skill) pair.
    assert required["skill_id"].is_unique
    assert required["skill_name"].str.lower().is_unique
    assert (required["job_count"] > 0).all()
    assert required["pct_of_role_jobs"].between(0, 100).all()

    # It reconciles with the flattened junction table the dashboard already uses.
    jobs = queries.get_all_jobs()
    links = queries.get_job_skill_links()
    role_job_ids = set(jobs.loc[jobs["job_title"] == role, "job_id"])
    expected = set(
        links.loc[links["job_id"].isin(role_job_ids), "skill_name"].str.casefold()
    )
    assert set(required["skill_name"].str.casefold()) == expected


@pytest.mark.usefixtures("database")
def test_role_lookup_is_case_insensitive_and_trimmed(database: str) -> None:
    role = str(queries.get_job_counts_by_role().iloc[0]["role"])
    expected = queries.get_required_skills_for_role(role)

    assert queries.get_required_skills_for_role(role.lower()).equals(expected)
    assert queries.get_required_skills_for_role(f"  {role.upper()}  ").equals(expected)


@pytest.mark.usefixtures("database")
def test_unknown_role_returns_no_skills_rather_than_everything(database: str) -> None:
    assert queries.get_required_skills_for_role("Astronaut").empty
    assert queries.get_required_skills_for_role("not a real role").empty


def test_blank_or_wrongly_typed_role_is_rejected_before_any_sql_runs() -> None:
    with pytest.raises(ValueError):
        queries.get_required_skills_for_role("   ")
    with pytest.raises(TypeError):
        queries.get_required_skills_for_role(42)  # type: ignore[arg-type]


@pytest.mark.usefixtures("database")
def test_skill_catalog_lists_every_skill_once(database: str) -> None:
    catalog = queries.get_skill_catalog()

    assert list(catalog.columns) == ["skill_id", "skill_name", "skill_category"]
    assert not catalog.empty
    assert catalog["skill_id"].is_unique
    assert catalog["skill_name"].str.casefold().is_unique


@pytest.mark.usefixtures("database")
def test_end_to_end_analysis_against_the_real_database(database: str) -> None:
    """The full path: database -> analysis -> numbers, for a real role."""
    catalog = queries.get_skill_catalog()
    role = "Machine Learning Engineer"
    if role not in set(queries.get_available_job_roles()["role"]):
        pytest.skip(f"the seed data has no '{role}' postings")

    required = queries.get_required_skills_for_role(role)

    # Holding every required skill is a full match, by definition.
    full = ui.analyze_skill_gap(required, ", ".join(required["skill_name"]), catalog, role=role)
    assert full.skill_match_pct == 100.0
    assert full.missing_count == 0

    # Holding none of them is a 0% match, with everything listed as missing.
    none_matched = ui.analyze_skill_gap(required, "QuantumFlux, NoSuchSkill", catalog, role=role)
    assert none_matched.skill_match_pct == 0.0
    assert none_matched.missing_count == required["skill_id"].nunique()
    assert set(none_matched.unrecognized) == {"QuantumFlux", "NoSuchSkill"}

    # A half match is exactly half, computed by hand.
    half_the_skills = required["skill_name"].tolist()[: required["skill_id"].nunique() // 2]
    partial = ui.analyze_skill_gap(required, ", ".join(half_the_skills), catalog, role=role)
    assert partial.matched_count == len(half_the_skills)
    assert partial.skill_match_pct == pytest.approx(
        100.0 * len(half_the_skills) / required["skill_id"].nunique()
    )


# ---------------------------------------------------------------------------
# 10. The SQL uses parameterized values
# ---------------------------------------------------------------------------


def _sql_argument_of(function) -> ast.AST:
    """Return the first argument node of the ``fetch_dataframe(...)`` call."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "fetch_dataframe"
        ):
            return node.args[0]
    raise AssertionError(f"{function.__name__} does not call fetch_dataframe()")


@pytest.mark.parametrize(
    ("function", "expect_placeholder"),
    [
        (queries.get_required_skills_for_role, True),
        (queries.get_available_job_roles, False),
        (queries.get_skill_catalog, False),
    ],
    ids=lambda value: getattr(value, "__name__", str(value)),
)
def test_new_sql_is_a_static_string_with_psycopg_placeholders(
    function, expect_placeholder: bool
) -> None:
    """The SQL must be a literal, never an f-string or a %-formatted template.

    An f-string or a ``%`` interpolation in the SQL text is exactly how a value
    would end up as executable SQL, so it is rejected structurally rather than
    trusted to review. The placeholder check is only meaningful for the query
    that actually takes a parameter; the other two read no user input at all.
    """
    sql_node = _sql_argument_of(function)

    assert isinstance(sql_node, ast.Constant), (
        f"{function.__name__} builds its SQL dynamically; pass values as "
        "fetch_dataframe parameters instead."
    )
    assert isinstance(sql_node.value, str)
    assert ("%s" in sql_node.value) is expect_placeholder, (
        f"{function.__name__} should "
        f"{'use' if expect_placeholder else 'not use'} a psycopg placeholder"
    )


def test_role_is_bound_as_a_parameter_not_interpolated_into_sql() -> None:
    """The role must travel as a bound value in the params argument."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(queries.get_required_skills_for_role)))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "fetch_dataframe"
    ]

    assert len(calls) == 1
    call = calls[0]
    assert len(call.args) == 2, "the role must be passed as the params argument"
    assert isinstance(call.args[1], ast.Tuple), "params must be a tuple of values"
    assert len(call.args[1].elts) == 1

    # The SQL text holds one placeholder and no literal role name, so the role
    # can only ever arrive as a bound value.
    sql_text = call.args[0].value
    assert sql_text.count("%s") == 1
    assert not any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and len(node.value) > 12
        and node.value not in sql_text
        for node in ast.walk(call.args[1])
    )


@pytest.mark.usefixtures("database")
def test_sql_injection_through_the_role_is_treated_as_plain_text(database: str) -> None:
    """A role crafted like SQL is bound as data and simply matches nothing."""
    malicious = "'; DROP TABLE jobs; --"
    assert queries.get_required_skills_for_role(malicious).empty

    # The tables are untouched, and the genuine lookups still work.
    assert queries.get_table_row_counts().set_index("table_name")["row_count"]["jobs"] > 0
    role = str(queries.get_job_counts_by_role().iloc[0]["role"])
    assert not queries.get_required_skills_for_role(role).empty


@pytest.mark.usefixtures("database")
def test_skill_input_is_never_sent_to_the_database(database: str) -> None:
    """Typing SQL into the skill box is compared in Python, not executed.

    ``analyze_skill_gap`` takes no database handle at all, so the typed text
    cannot reach the driver. The proof is that a hostile string survives as an
    ordinary, unknown skill and the database is unchanged.
    """
    required = queries.get_required_skills_for_role(
        str(queries.get_job_counts_by_role().iloc[0]["role"])
    )
    hostile = "Python' OR '1'='1"

    result = ui.analyze_skill_gap(required, hostile, queries.get_skill_catalog())

    # The quote is just part of the name: it matches nothing and executes nothing.
    assert hostile in result.unrecognized
    assert result.skill_match_pct == 0.0
    assert int(
        queries.get_table_row_counts().set_index("table_name")["row_count"]["jobs"]
    ) > 0


# ---------------------------------------------------------------------------
# 11. Secrets
# ---------------------------------------------------------------------------


def test_the_feature_source_never_contains_the_database_password() -> None:
    """The real password must not appear in any file this feature added."""
    password = get_database_config()["DB_PASSWORD"]
    assert password, "DB_PASSWORD is empty, so this test would prove nothing"

    for relative in (
        "dashboard/app.py",
        "dashboard/components.py",
        "dashboard/styles.py",
        "src/data/queries.py",
        "tests/test_skill_gap.py",
    ):
        text = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        assert password not in text, f"the password leaked into {relative}"


def test_the_feature_source_does_not_manage_its_own_connection() -> None:
    """The new code reuses src.data.database; it never opens a connection."""
    app_source = (PROJECT_ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")
    components_source = (PROJECT_ROOT / "dashboard" / "components.py").read_text(encoding="utf-8")

    assert "psycopg.connect" not in app_source
    assert "psycopg.connect" not in components_source
    assert "get_connection" not in app_source
    assert "get_connection" not in components_source
    # components.py holds no database code at all.
    assert "fetch_dataframe" not in components_source
    assert "from src.data import queries" in app_source


def test_the_feature_adds_no_ml_or_llm_dependency() -> None:
    """The Skill Gap Analyzer stays a pure rule-based calculator.

    scikit-learn is now a project dependency, but only for the separate
    ``ml/`` recommender. This test pins that the *baseline* neither imports it
    nor depends on it, so the two scoring paths can never quietly merge.
    """
    for relative in (
        "dashboard/app.py",
        "dashboard/components.py",
        "src/data/queries.py",
    ):
        tree = ast.parse((PROJECT_ROOT / relative).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert "sklearn" not in imported, f"{relative} imports scikit-learn"

    # No LLM or neural-network client anywhere in the project.
    text = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    declared = " ".join(
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )
    for banned in (
        "openai",
        "groq",
        "huggingface",
        "transformers",
        "sentence-transformers",
        "langchain",
        "tensorflow",
        "torch",
        "pytorch",
        "rapidfuzz",
        "fuzzywuzzy",
    ):
        assert banned not in declared, f"{banned} was added to requirements.txt"


# ---------------------------------------------------------------------------
# 12. End to end: the tab inside the real Streamlit app
# ---------------------------------------------------------------------------


def _run_app():
    from streamlit.testing.v1 import AppTest

    return AppTest.from_file(str(PROJECT_ROOT / "dashboard" / "app.py"), default_timeout=180)


def _rendered_text(app) -> str:
    """Every visible text block of the app, as one searchable string."""
    blocks = [block.value for block in app.markdown]
    blocks += [str(value.value) for value in app.info]
    blocks += [str(value.value) for value in app.warning]
    blocks += [str(value.value) for value in app.success]
    blocks += [str(value.value) for value in app.caption]
    return "\n".join(blocks)


#: The Skill Gap Analyzer's widgets are addressed by key, never by position.
#: Streamlit orders widgets by execution, and the Salary and Recent Jobs tabs
#: both own a selectbox and a text input that come earlier in the page.
ROLE_BOX = "skill_gap_role"
SKILLS_BOX = "skill_gap_skills"
ANALYZE_BUTTON = "skill_gap_analyze"


@pytest.mark.usefixtures("database")
def test_skill_gap_tab_asks_for_a_role_and_skills_before_analysing(database: str) -> None:
    """The tab opens with its two controls and an explicit prompt."""
    app = _run_app()
    app.run()
    assert not app.exception, [f"{e.type}: {e.message}" for e in app.exception]

    assert ANALYZE_BUTTON in [button.key for button in app.button]
    assert app.selectbox(key=ROLE_BOX).label == "Target role"
    assert app.text_input(key=SKILLS_BOX).label == "Your current skills"
    assert "Analyze Skills" in _rendered_text(app)


@pytest.mark.usefixtures("database")
def test_skill_gap_tab_reports_the_real_percentage(database: str) -> None:
    """Clicking Analyze must show the same number the data layer computes."""
    app = _run_app()
    app.run()

    app.text_input(key=SKILLS_BOX).set_value("Python, SQL, Pandas, Git, Docker")
    app.button(key=ANALYZE_BUTTON).click()
    app.run()
    assert not app.exception, [f"{e.type}: {e.message}" for e in app.exception]

    selected = app.selectbox(key=ROLE_BOX).value
    required = queries.get_required_skills_for_role(selected)
    expected = ui.analyze_skill_gap(
        required, "Python, SQL, Pandas, Git, Docker", queries.get_skill_catalog(), role=selected
    )

    rendered = _rendered_text(app)
    assert expected.role in rendered
    assert f'gap-hero-pct">{expected.skill_match_text}<' in rendered
    assert "Python" in rendered
    # The match can never be claimed above 100%, whatever the seed data holds.
    assert expected.skill_match_pct <= 100.0


@pytest.mark.usefixtures("database")
def test_skill_gap_tab_handles_empty_input_with_a_message(database: str) -> None:
    """Empty input must produce the documented message, not a traceback."""
    app = _run_app()
    app.run()

    app.text_input(key=SKILLS_BOX).set_value("   ")
    app.button(key=ANALYZE_BUTTON).click()
    app.run()
    assert not app.exception, [f"{e.type}: {e.message}" for e in app.exception]
    assert "Please enter at least one skill." in _rendered_text(app)


@pytest.mark.usefixtures("database")
def test_skill_gap_tab_handles_an_unknown_skill_with_a_message(database: str) -> None:
    """An unknown skill warns, and the recognised skills are still scored."""
    app = _run_app()
    app.run()

    app.text_input(key=SKILLS_BOX).set_value("Python, QuantumFlux")
    app.button(key=ANALYZE_BUTTON).click()
    app.run()
    assert not app.exception, [f"{e.type}: {e.message}" for e in app.exception]

    rendered = _rendered_text(app)
    assert "Some entered skills were not found in the job-market skill database." in rendered
    assert "QuantumFlux" in rendered


@pytest.mark.usefixtures("database")
def test_skill_gap_tab_reaches_a_full_match(database: str) -> None:
    """Typing every required skill of a role gives a 100% match card."""
    app = _run_app()
    app.run()

    role = "Machine Learning Engineer"
    if role not in set(queries.get_available_job_roles()["role"]):
        pytest.skip(f"the seed data has no '{role}' postings")

    app.selectbox(key=ROLE_BOX).select(role)
    app.run()
    assert not app.exception, [f"{e.type}: {e.message}" for e in app.exception]

    required = queries.get_required_skills_for_role(role)
    app.text_input(key=SKILLS_BOX).set_value(", ".join(required["skill_name"]))
    app.button(key=ANALYZE_BUTTON).click()
    app.run()
    assert not app.exception, [f"{e.type}: {e.message}" for e in app.exception]

    assert 'gap-hero-pct">100%<' in _rendered_text(app)

