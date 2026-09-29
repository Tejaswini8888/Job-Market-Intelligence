r"""Tests for the Role Recommendation Engine.

Like the Skill Gap tests, these come in two tiers that never depend on each
other:

* **Pure logic** - normalisation, union-aggregation, TF-IDF ranking, score
  bounds, ties, empty and unknown-skill edges, and the ``top_n`` contract.
  Everything runs against small hand-written corpora whose outcomes are known
  by hand, so no database is needed.
* **Database-backed** - role profiles and recommendations really built from
  PostgreSQL. These are skipped (not failed) when the database is unreachable,
  exactly like the other two test modules.

The maths properties asserted here are deliberately coarse (ordering and
bounds, not re-implemented IDF arithmetic): re-deriving scikit-learn's exact
cosine values would only prove the test and the library agree with their own
conventions, while ordering and bounds prove the interface behaves.

No test contains a password, and one test scans the ``ml/`` sources to prove
they neither import an external client nor embed credentials.

Run with::

    .\.venv\Scripts\Activate.ps1
    python -m pytest -v
"""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest

from ml.preprocessing import (
    ROLE_PROFILE_COLUMNS,
    build_job_skill_documents,
    build_role_profiles,
    build_user_document,
    compare_skill_sets,
    normalize_skill_name,
    parse_skill_list,
)
from ml.recommender import (
    RECOMMENDATION_COLUMNS,
    RoleRecommender,
    load_role_profiles,
    model_information,
    recommend_with_diagnostics,
    recommend_roles,
    skill_document_analyzer,
)
from src.data.database import test_connection as check_connection

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Synthetic corpus whose ranking is known by hand.
#
# Data Engineer needs Python + CUDA, Backend Engineer needs Python,
# Security Engineer needs Java. The query "Python, CUDA" must therefore rank
# Data Engineer first with a perfect 100.0 (the query vector is exactly that
# role's document vector), Backend Engineer second (shares Python), and
# Security Engineer last with 0.0 (no shared skill).
# ---------------------------------------------------------------------------

def _profiles(
    rows: list[dict[str, object]],
) -> pd.DataFrame:
    """Turn compact row dicts into a frame with the full profile layout."""
    for row in rows:
        row.setdefault("job_count", 0)
        row.setdefault("required_count", len(row["required_skills"]))  # type: ignore[arg-type]
        row.setdefault("skill_frequencies", {})
    return pd.DataFrame(rows, columns=list(ROLE_PROFILE_COLUMNS))


CORPUS = _profiles(
    [
        {
            "role": "Data Engineer",
            "required_skills": ("Python", "CUDA"),
            "document": ("python", "cuda"),
        },
        {
            "role": "Backend Engineer",
            "required_skills": ("Python",),
            "document": ("python",),
        },
        {
            "role": "Security Engineer",
            "required_skills": ("Java",),
            "document": ("java",),
        },
    ]
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
    """Skip the test unless the local PostgreSQL database is reachable."""
    if not _DATABASE_AVAILABLE:
        pytest.skip(
            "This test needs a running local PostgreSQL database and DB_USER / "
            "DB_PASSWORD in .env. Reason: " + _DATABASE_REASON
        )
    return _DATABASE_REASON


# ---------------------------------------------------------------------------
# 1. Normalisation - the single source of truth shared with the Skill Gap tab
# ---------------------------------------------------------------------------


def test_normalize_skill_name_trims_and_casefolds() -> None:
    assert normalize_skill_name("  PyTorch ") == "pytorch"
    assert normalize_skill_name("Apache   Spark") == "apache spark"
    assert normalize_skill_name("SQL") == "sql"


def test_normalize_skill_name_rejects_non_strings() -> None:
    with pytest.raises(TypeError):
        normalize_skill_name(42)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        normalize_skill_name(None)  # type: ignore[arg-type]


def test_parse_skill_list_deduplicates_case_insensitively_keeps_first_spelling() -> None:
    parsed = parse_skill_list("Python, SQL,  python ,Git\nDocker|C++")
    assert parsed == ["Python", "SQL", "Git", "Docker", "C++"]


def test_parse_skill_list_preserves_multi_word_and_dotted_names() -> None:
    parsed = parse_skill_list("CI/CD, C++, Apache Spark")
    assert parsed == ["CI/CD", "C++", "Apache Spark"]


def test_parse_skill_list_handles_empty_input() -> None:
    assert parse_skill_list(None) == []
    assert parse_skill_list("") == []
    assert parse_skill_list("  , ;\n ") == []


def test_parse_skill_list_rejects_non_strings() -> None:
    with pytest.raises(TypeError):
        parse_skill_list(42)  # type: ignore[arg-type]


def test_build_user_document_normalises_to_casefolded_tuple() -> None:
    assert build_user_document("Python, MySQL, mysql") == ("python", "mysql")


# ---------------------------------------------------------------------------
# 2. Posting documents and role-profile aggregation
# ---------------------------------------------------------------------------


def test_build_job_skill_documents_collapses_duplicate_skill_rows() -> None:
    links = pd.DataFrame(
        {
            "job_id": [1, 1, 1, 2],
            "skill_name": ["Python", "python", "SQL", "Docker"],
        }
    )
    jobs = pd.DataFrame({"job_id": [1, 2], "job_title": ["Data Engineer", "DevOps"]})
    documents = build_job_skill_documents(links, jobs)
    row = documents.loc[documents["job_id"] == 1].iloc[0]
    assert row["skills"] == ("Python", "SQL")
    assert row["document"] == ("python", "sql")
    assert row["skill_count"] == 2


def test_build_role_profiles_unions_skills_across_postings_for_one_role() -> None:
    documents = pd.DataFrame(
        {
            "job_id": [1, 2, 3],
            "job_title": ["Data Engineer", "Data Engineer", "Security Engineer"],
            "skills": [
                ("Python", "Apache Spark"),
                ("Python", "Apache Airflow"),
                ("Python",),
            ],
            "document": [
                ("python", "apache spark"),
                ("python", "apache airflow"),
                ("python",),
            ],
            "skill_count": [2, 2, 1],
        }
    )
    profiles = build_role_profiles(documents)
    engineer = profiles.loc[profiles["role"] == "Data Engineer"].iloc[0]
    assert engineer["job_count"] == 2
    assert engineer["required_count"] == 3
    # Most frequent first (python, from both postings), then alphabetical.
    assert engineer["document"] == ("python", "apache airflow", "apache spark")
    assert engineer["required_skills"] == ("Python", "Apache Airflow", "Apache Spark")


def test_build_role_profiles_sorts_by_required_count_then_name() -> None:
    documents = pd.DataFrame(
        {
            "job_id": [1, 2, 3, 4],
            "job_title": ["Role A", "Role B", "Role C", "Role D"],
            "skills": [
                ("Pandas", "Numpy", "Scipy"),
                ("Pandas", "Numpy"),
                ("Pandas",),
                ("Pandas", "Numpy"),
            ],
            "document": [
                ("pandas", "numpy", "scipy"),
                ("pandas", "numpy"),
                ("pandas",),
                ("pandas", "numpy"),
            ],
            "skill_count": [3, 2, 1, 2],
        }
    )
    profiles = build_role_profiles(documents)
    assert profiles["role"].tolist() == ["Role A", "Role B", "Role D", "Role C"]


def test_build_job_skill_documents_empty_input_returns_typed_layout() -> None:
    for source in (
        None,
        pd.DataFrame(),
        pd.DataFrame({"job_id": [1, 2], "skill_name": [None, " "]}),
    ):
        empty = build_job_skill_documents(source)  # type: ignore[arg-type]
        assert empty.empty
        assert list(empty.columns) == list(("job_id", "job_title", "skills", "document", "skill_count"))


def test_build_role_profiles_empty_input_returns_typed_layout() -> None:
    empty = build_role_profiles(pd.DataFrame())
    assert empty.empty
    assert list(empty.columns) == list(ROLE_PROFILE_COLUMNS)


def test_build_job_skill_documents_requires_expected_columns() -> None:
    with pytest.raises(ValueError):
        build_job_skill_documents(pd.DataFrame({"wrong": [1]}))


def test_build_role_profiles_requires_expected_columns() -> None:
    with pytest.raises(ValueError):
        build_role_profiles(pd.DataFrame({"role": ["x"]}))


# ---------------------------------------------------------------------------
# 3. Classic rule-based overlap (the baseline next to the score)
# ---------------------------------------------------------------------------


def test_compare_skill_sets_is_case_insensitive_and_keeps_database_spelling() -> None:
    matched, missing = compare_skill_sets(
        ["PyTorch", "TensorFlow", "Keras"], ["tensorflow", "PYTORCH"]
    )
    assert matched == ["PyTorch", "TensorFlow"]
    assert missing == ["Keras"]


# ---------------------------------------------------------------------------
# 4. Ranking: score, ordering, bounds and ties
# ---------------------------------------------------------------------------


def test_perfect_overlap_scores_100_exactly() -> None:
    results = recommend_roles("Python, CUDA", CORPUS, top_n=3)
    top = results.iloc[0]
    assert top["role"] == "Data Engineer"
    assert top["score"] == 100.0
    assert top["matched_skills"] == ("Python", "CUDA")
    assert top["missing_skills"] == ()
    assert top["rule_based_pct"] == 100.0


def test_partial_overlap_ranks_between_perfect_and_none() -> None:
    results = recommend_roles("Python, CUDA", CORPUS, top_n=3)
    scores = dict(zip(results["role"], results["score"]))
    assert scores["Backend Engineer"] < 100.0
    assert scores["Backend Engineer"] > 0.0
    assert scores["Security Engineer"] == 0.0


def test_ranking_order_matches_shared_vocabulary() -> None:
    results = recommend_roles("Python, CUDA", CORPUS, top_n=3)
    assert results["role"].tolist() == [
        "Data Engineer",
        "Backend Engineer",
        "Security Engineer",
    ]


def test_one_role_appears_at_most_once_even_if_query_repeats_it() -> None:
    results = recommend_roles("Python, CUDA, python, Python", CORPUS, top_n=3)
    assert results["role"].nunique() == len(results)


def test_a_shared_rare_skill_outweighs_a_shared_common_skill() -> None:
    # python appears in three roles, pandas in two, so pandas is rarer and its
    # IDF weight is higher. Two roles each share exactly one of the two query
    # skills, so the role sharing (only) the rarer Pandas term must rank higher
    # than the one sharing (only) the common Python term.
    corpus = _profiles(
        [
            {"role": "R1", "required_skills": ("Python", "Pandas", "Java"), "document": ("python", "pandas", "java")},
            {"role": "R2", "required_skills": ("Python",), "document": ("python",)},
            {"role": "R3", "required_skills": ("Pandas",), "document": ("pandas",)},
            {"role": "R4", "required_skills": ("Python", "Git"), "document": ("python", "git")},
        ]
    )
    results = recommend_roles("Python, Pandas", corpus, top_n=4)
    scores = dict(zip(results["role"], results["score"]))
    assert scores["R3"] > scores["R2"] > 0.0


def test_scores_are_between_0_and_100_with_one_decimal() -> None:
    results = recommend_roles("Python, CUDA", CORPUS, top_n=3)
    assert results["score"].between(0.0, 100.0).all()
    assert all(round(value, 1) == value for value in results["score"])


def test_ties_break_alphabetically_not_by_input_order() -> None:
    corpus = _profiles(
        [
            {"role": "beta", "required_skills": ("Python",), "document": ("python",)},
            {"role": "alpha", "required_skills": ("Python",), "document": ("python",)},
        ]
    )
    results = recommend_roles("python", corpus, top_n=2)
    assert results["role"].tolist() == ["alpha", "beta"]


def test_recommendation_is_deterministic() -> None:
    first = recommend_roles("Python, CUDA", CORPUS, top_n=3)
    second = recommend_roles("Python, CUDA", CORPUS, top_n=3)
    assert first.equals(second)


def test_result_frame_has_exactly_the_documented_columns() -> None:
    results = recommend_roles("Python, CUDA", CORPUS, top_n=3)
    assert list(results.columns) == list(RECOMMENDATION_COLUMNS)


def test_matched_missing_and_required_counts_tally() -> None:
    results = recommend_roles("Python, CUDA", CORPUS, top_n=3)
    for _, row in results.iterrows():
        assert row["matched_count"] == len(row["matched_skills"])
        assert row["missing_count"] == len(row["missing_skills"])
        assert row["required_count"] == len(row["required_skills"])
        assert row["matched_count"] + row["missing_count"] == row["required_count"]
        assert row["rule_based_pct"] == round(
            100.0 * row["matched_count"] / row["required_count"], 1
        )


def test_fit_happens_once_and_query_cannot_change_the_vocabulary() -> None:
    engine = RoleRecommender(CORPUS)
    vocabulary = dict(engine._vectorizer.vocabulary_)
    engine.recommend("python, cuda, brand new skill", top_n=3)
    assert engine._vectorizer.vocabulary_ == vocabulary


# ---------------------------------------------------------------------------
# 5. Edge cases: empty and unknown input, top_n
# ---------------------------------------------------------------------------


def test_empty_input_returns_empty_typed_result_not_an_error() -> None:
    for empty_input in ("", "   ", " , ;\n ", None):
        results = recommend_roles(empty_input, CORPUS, top_n=3)  # type: ignore[arg-type]
        assert results.empty
        assert list(results.columns) == list(RECOMMENDATION_COLUMNS)


def test_only_unknown_skills_return_an_empty_ranking() -> None:
    results = recommend_roles("Quantum Computing, COBOL", CORPUS, top_n=3)
    assert results.empty


def test_diagnostics_explain_why_there_is_nothing_to_rank() -> None:
    diag = recommend_with_diagnostics("", CORPUS)
    assert diag["status"] == "no_skills"
    assert "at least one skill" in diag["message"]

    diag = recommend_with_diagnostics("Quantum Computing", CORPUS)
    assert diag["status"] == "no_known_skills"
    assert diag["known"] == []
    assert diag["unknown"] == ["Quantum Computing"]

    diag = recommend_with_diagnostics("Python, COBOL", CORPUS)
    assert diag["status"] == "ok"
    assert diag["known"] == ["Python"]
    assert diag["unknown"] == ["COBOL"]


def test_top_n_larger_than_available_roles_returns_them_all() -> None:
    results = recommend_roles("Python, CUDA", CORPUS, top_n=10_000)
    assert len(results) == 3


def test_top_n_respects_the_requested_cap() -> None:
    results = recommend_roles("Python, CUDA", CORPUS, top_n=1)
    assert len(results) == 1
    assert results.iloc[0]["role"] == "Data Engineer"


def test_top_n_zero_or_negative_is_rejected() -> None:
    with pytest.raises(ValueError):
        recommend_roles("Python", CORPUS, top_n=0)
    with pytest.raises(ValueError):
        recommend_roles("Python", CORPUS, top_n=-3)


def test_top_n_non_integral_is_rejected() -> None:
    with pytest.raises(TypeError):
        recommend_roles("Python", CORPUS, top_n="5")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        recommend_roles("Python", CORPUS, top_n=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        recommend_roles("Python", CORPUS, top_n=5.0)  # type: ignore[arg-type]


def test_empty_role_corpus_is_degenerate_not_fatal() -> None:
    engine = RoleRecommender(pd.DataFrame())
    assert engine.role_count == 0
    assert engine.vocabulary_size == 0
    assert not engine.is_known_skill("python")
    assert engine.recommend("Python").empty
    assert engine.similarity("Python").empty


def test_diagnostics_over_empty_corpus_reports_no_roles() -> None:
    diag = recommend_with_diagnostics("Python", pd.DataFrame())
    assert diag["status"] == "no_roles"
    assert "nothing to recommend" in diag["message"]
    assert diag["results"].empty


# ---------------------------------------------------------------------------
# 6. One skill = one TF-IDF term
# ---------------------------------------------------------------------------


def test_multi_word_skill_is_one_term_not_three_words() -> None:
    corpus = _profiles(
        [
            {"role": "ML Engineer", "required_skills": ("Machine Learning", "Deep Learning"), "document": ("machine learning", "deep learning")},
            {"role": "Backend", "required_skills": ("Python",), "document": ("python",)},
        ]
    )
    engine = RoleRecommender(corpus)
    assert engine.vocabulary_size == 3
    assert engine.is_known_skill("Machine Learning")
    assert not engine.is_known_skill("Learning")
    # "learning" is not a skill in this market even though it is a word inside
    # the "Machine Learning" term: tokenisation never happens.
    assert recommend_roles("Learning", corpus, top_n=2).empty


def test_skill_document_analyzer_passes_the_document_through() -> None:
    # The vectoriser's analyzer must hand back the skill list unchanged: no
    # whitespace splitting, no tokenisation.
    assert skill_document_analyzer(["Machine Learning", "C++"]) == [
        "Machine Learning",
        "C++",
    ]


def test_split_known_skills_keeps_users_own_spelling_and_order() -> None:
    corpus = _profiles(
        [
            {"role": "R", "required_skills": ("Python", "PyTorch"), "document": ("python", "pytorch")},
        ]
    )
    engine = RoleRecommender(corpus)
    known, unknown = engine.split_known_skills("PyTorch, pandas, PYTORCH")
    assert known == ["PyTorch"]
    assert unknown == ["pandas"]


# ---------------------------------------------------------------------------
# 7. Model information - honest, dynamic, not a hardcoded claim
# ---------------------------------------------------------------------------


def test_model_information_reports_real_counts() -> None:
    info = model_information(CORPUS)
    assert info["role_count"] == 3
    assert info["vocabulary_size"] == 3
    assert info["postings_represented"] == 0  # fixtures carry no job_count
    assert info["method"].startswith("TF-IDF")
    assert "prototype, not a trained or validated model" in info["limitations"]
    assert len(info["steps"]) == 5
    assert "no external service" in info["no_external_services"].lower() or "scikit-learn" in info["no_external_services"]


# ---------------------------------------------------------------------------
# 8. No external clients, no credentials in the ml layer
# ---------------------------------------------------------------------------


def test_the_ml_layer_uses_only_local_scikit_learn() -> None:
    banned = {
        "openai", "groq", "anthropic", "requests", "httpx", "urllib", "aiohttp",
        "torch", "tensorflow", "transformers", "langchain", "sentence_transformers",
        "rapidfuzz", "fuzzywuzzy", "difflib",
    }
    for relative in (
        "ml/preprocessing.py",
        "ml/recommender.py",
        "ml/__init__.py",
    ):
        tree = ast.parse((PROJECT_ROOT / relative).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not (imported & banned), (
            f"{relative} imports {sorted(imported & banned)}"
        )


def test_the_ml_layer_contains_no_database_credentials() -> None:
    for relative in ("ml/preprocessing.py", "ml/recommender.py", "ml/__init__.py"):
        text = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        assert "DB_PASSWORD" not in text, f"{relative} mentions DB_PASSWORD"
        assert "password" not in text.casefold(), f"{relative} mentions a password"


# ---------------------------------------------------------------------------
# 9. The real database: profiles straight from PostgreSQL, and recommendations
#    that stay consistent with the rule-based baseline.
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("database")
def test_load_role_profiles_against_the_real_database(database: str) -> None:
    profiles = load_role_profiles()
    assert list(profiles.columns) == list(ROLE_PROFILE_COLUMNS)
    assert len(profiles) == 12, "the seed defines 12 job roles"
    assert profiles["role"].is_unique
    assert (profiles["required_count"] > 0).all()
    assert int(profiles["job_count"].sum()) == 40, "the seed defines 40 postings"


@pytest.mark.usefixtures("database")
def test_recommend_against_the_real_database_is_sane_and_deterministic(database: str) -> None:
    query = "Python, SQL, Pandas, Git, Docker"
    first = recommend_roles(query, top_n=5)
    second = recommend_roles(query, top_n=5)
    assert first.equals(second)
    assert len(first) == 5
    assert first["score"].between(0.0, 100.0).all()
    for _, row in first.iterrows():
        assert row["matched_count"] + row["missing_count"] == row["required_count"]
        assert row["rule_based_pct"] == round(
            100.0 * row["matched_count"] / row["required_count"], 1
        )


@pytest.mark.usefixtures("database")
def test_real_database_top_n_larger_than_role_count_returns_all(database: str) -> None:
    results = recommend_roles("Python, SQL", top_n=10_000)
    assert len(results) == 12


@pytest.mark.usefixtures("database")
def test_real_database_diagnostics_report_ok_for_known_skills(database: str) -> None:
    diag = recommend_with_diagnostics("Python, SQL, Pandas", top_n=5)
    assert diag["status"] == "ok"
    assert diag["known"] == ["Python", "SQL", "Pandas"]
    assert diag["unknown"] == []
    assert not diag["results"].empty


@pytest.mark.usefixtures("database")
def test_real_database_vocabulary_matches_the_seed(database: str) -> None:
    profiles = load_role_profiles()
    engine = RoleRecommender(profiles)
    assert engine.vocabulary_size == 32, "the seed defines 32 distinct skills"