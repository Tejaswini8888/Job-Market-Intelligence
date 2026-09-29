"""TF-IDF + cosine similarity role recommender.

What this does
--------------
Given the skills someone already has, rank the job roles in the database whose
required skills are most similar. The method is the classic bag-of-words
retrieval pipeline and nothing more:

1. Each role becomes a **document**: every skill any of its postings requires.
2. :class:`sklearn.feature_extraction.text.TfidfVectorizer` turns that document
   into a vector, weighting each skill by how rare it is across roles, so a
   skill every role wants (``Python``) counts for less than one only the role
   wants (``PyTorch``).
3. The user's skills become a vector with the same vocabulary.
4. :func:`sklearn.metrics.pairwise.cosine_similarity` measures the angle
   between the two, on a 0-1 scale.
5. The score is shown as ``similarity * 100``, rounded to one decimal, and is
   called the **Skill Similarity Score**.

Two deliberate choices, both made for explainability
----------------------------------------------------
**One skill is one term.** The vectoriser runs with a callable analyzer that
treats the document as an already-split list of skills, instead of splitting
text on whitespace. With default tokenisation "Machine Learning" and "Deep
Learning" would each become two terms and share the token ``learning``, so a
user with no ML background would look partly like an ML engineer. Here they are
two single terms and only count for each other when they actually match.

**IDF is fitted on the roles, not on the query.** The vectoriser is fitted once
on the role corpus and the user's skills are only *transformed* with it. This is
standard retrieval practice: it keeps the importance weights a property of the
market being searched, so adding a skill to the query cannot change what
"important" means for any other role.

What the score is not
---------------------
It is **not** a probability, **not** a confidence, and **not** a prediction of
whether the person will get the job or succeed in it. It is one number saying:
*these two lists of skill names point in a similar direction*. The most
important thing to know when reading it is the limitation in
:data:`MODEL_LIMITATIONS` - this is a prototype over a small, synthetic,
vocabulary, not a trained model with any measured accuracy.

Use
---
    from ml.recommender import recommend_roles, load_role_profiles

    profiles = load_role_profiles()          # one row per role, from PostgreSQL
    results = recommend_roles("Python, SQL, Pandas, Git, Docker", profiles, top_n=5)
    results[["role", "score"]]

For a reusable, repeatedly-scored model, hold the object instead::

    engine = RoleRecommender(profiles)
    engine.recommend("Python, SQL")   # the vectoriser is fitted once, on __init__
"""

from __future__ import annotations

from typing import Any, Sequence

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ml.preprocessing import (
    ROLE_PROFILE_COLUMNS,
    build_job_skill_documents,
    build_role_profiles,
    build_user_document,
    compare_skill_sets,
    normalize_skill_name,
    parse_skill_list,
)

#: Default number of roles returned by :func:`recommend_roles`.
DEFAULT_TOP_N: int = 5

#: Column layout of the frame returned by :func:`recommend_roles`.
RECOMMENDATION_COLUMNS: tuple[str, ...] = (
    "role",
    "score",
    "matched_skills",
    "missing_skills",
    "required_skills",
    "matched_count",
    "missing_count",
    "required_count",
    "rule_based_pct",
    "job_count",
)

#: Stated in the UI next to the results. Deliberately blunt: a prototype over a
#: small synthetic dataset must not be mistaken for a validated model. The real
#: row counts are injected by :func:`model_information` rather than hardcoded
#: here, so this text can never drift away from the data it describes.
MODEL_LIMITATIONS: str = (
    "This is a prototype, not a trained or validated model. It runs on a small, "
    "synthetic dataset, so the inverse document frequency weights are estimated "
    "from very few role profiles and a single skill can move a score a long "
    "way. The score has not been validated against any outcome data - there is "
    "no outcome data here to validate it against - so no accuracy, precision or "
    "recall figure is claimed for it. Treat it as a transparent way to rank "
    "role descriptions by shared vocabulary, and read it alongside the "
    "rule-based skill match."
)

#: What the two numbers mean, side by side. Neither is "the correct one".
MODEL_COMPARISON: tuple[tuple[str, str], ...] = (
    (
        "Rule-Based Skill Match",
        "Counts how many of a role's required skills you already have, divided "
        "by how many it requires. Pure set arithmetic: it is either a match or "
        "it is not, and it ignores how common a skill is. A role that needs ten "
        "skills scores lower than one that needs four for the same absolute "
        "number of matches.",
    ),
    (
        "ML Skill Similarity",
        "Scores the overlap through TF-IDF and cosine similarity, so a shared "
        "rare skill counts for more than a shared common one, and a short "
        "profile is not penalised the way a plain ratio penalises it. It also "
        "ignores how many skills the role actually requires, so it says how "
        "similar two lists are, not how complete yours is.",
    ),
    (
        "Read them together",
        "They answer different questions. The rule-based number measures "
        "coverage - how much of the requirement set you meet. The similarity "
        "number measures resemblance - how much your skills look like this "
        "role's. A high similarity with a low match means the role is adjacent "
        "to you but out of reach; a high match with middling similarity means "
        "you already cover most of a role that is not especially close to you. "
        "Neither is automatically the better number, and neither is a "
        "probability of getting the job.",
    ),
)


def skill_document_analyzer(document: Any) -> Sequence[str]:
    """The analyzer that makes one skill equal one TF-IDF term.

    scikit-learn's default analyzer splits text on word boundaries. That is
    wrong for skill names, because "Apache Spark" and "Spark" would be treated
    as unrelated, and "Machine Learning" and "Deep Learning" would share the
    token "learning". Documents here are already lists of normalised skill
    names, so this analyzer simply passes them through.

    It is a module-level function rather than a lambda so the vectoriser stays
    inspectable and copyable.
    """
    return document


def _validate_top_n(top_n: Any) -> int:
    """Return ``top_n`` if it is a sane positive integer, else raise.

    There is no upper bound: a request for more roles than exist is not an
    error, it simply returns them all (see :meth:`RoleRecommender.recommend`).
    """
    if isinstance(top_n, bool) or not isinstance(top_n, int):
        raise TypeError(f"top_n must be an int, got {type(top_n).__name__}.")
    if top_n < 1:
        raise ValueError(f"top_n must be 1 or greater, got {top_n}.")
    return top_n


def _empty_recommendations() -> pd.DataFrame:
    """An empty recommendations frame carrying the full column layout."""
    return pd.DataFrame(
        {
            "role": pd.Series(dtype="object"),
            "score": pd.Series(dtype="float64"),
            "matched_skills": pd.Series(dtype="object"),
            "missing_skills": pd.Series(dtype="object"),
            "required_skills": pd.Series(dtype="object"),
            "matched_count": pd.Series(dtype="int64"),
            "missing_count": pd.Series(dtype="int64"),
            "required_count": pd.Series(dtype="int64"),
            "rule_based_pct": pd.Series(dtype="float64"),
            "job_count": pd.Series(dtype="int64"),
        }
    )


class RoleRecommender:
    """A fitted TF-IDF index over job-role skill profiles.

    Construct it once from :func:`ml.preprocessing.build_role_profiles` and call
    :meth:`recommend` as often as you like: the vectoriser is fitted in
    ``__init__`` and never refitted, so a query can never influence the
    vocabulary or the importance weights.

    :param role_profiles: one row per role, with ``role``, ``required_skills``
        and ``document`` columns (the output of
        ``ml.preprocessing.build_role_profiles``).
    :param smooth_idf: passed straight to :class:`TfidfVectorizer`. It defaults
        to ``True`` in scikit-learn, which is kept, because with a vocabulary
        this small an unsmoothed IDF would divide by zero for any skill that
        every single role happens to require.

    Fitting is deterministic - no sampling, no shuffling, no random state - so
    the same profiles always produce the same ranking.
    """

    def __init__(self, role_profiles: pd.DataFrame) -> None:
        self.role_profiles = self._validate_profiles(role_profiles)
        documents = list(self.role_profiles["document"])
        self.roles: tuple[str, ...] = tuple(
            str(role) for role in self.role_profiles["role"]
        )
        # An empty corpus is a degenerate case, not an error: with nothing to
        # rank, fit is skipped entirely rather than handed an empty list (which
        # would raise "empty vocabulary"). Every scoring method checks
        # ``_fitted`` first, so an empty recommender "knows nothing" instead of
        # crashing.
        self._vectorizer = TfidfVectorizer(
            analyzer=skill_document_analyzer,
            lowercase=False,  # names are already case-folded
            norm="l2",  # cosine similarity needs unit-length rows
            sublinear_tf=False,
        )
        if documents:
            self._matrix = self._vectorizer.fit_transform(documents)
            self._fitted = True
        else:
            self._matrix = None
            self._fitted = False

    # -- introspection, used by the UI's "how this works" panel ----------------

    @staticmethod
    def _validate_profiles(role_profiles: pd.DataFrame | None) -> pd.DataFrame:
        if role_profiles is None or len(role_profiles) == 0:
            return pd.DataFrame(columns=list(ROLE_PROFILE_COLUMNS))
        for column in ("role", "required_skills", "document"):
            if column not in role_profiles.columns:
                raise ValueError(
                    f"role_profiles must have a {column!r} column; build it with "
                    "ml.preprocessing.build_role_profiles()."
                )
        return role_profiles

    @property
    def role_count(self) -> int:
        """How many roles this recommender can rank."""
        return int(len(self.roles))

    @property
    def vocabulary_size(self) -> int:
        """How many distinct skills the TF-IDF vocabulary learned."""
        return int(len(self._vectorizer.vocabulary_)) if self._fitted else 0

    def is_known_skill(self, skill: str) -> bool:
        """Whether ``skill`` is a term in the fitted vocabulary.

        Skills outside it cannot influence the score at all, which is how the
        recommender reports "this market has never heard of that skill" instead
        of silently ignoring it.
        """
        return self._fitted and normalize_skill_name(skill) in self._vectorizer.vocabulary_

    def split_known_skills(self, user_skills: str | Sequence[str] | None) -> tuple[list[str], list[str]]:
        """Split typed skills into ``(known, unknown)``.

        Both lists keep the user's own spelling and order. ``known`` is the part
        of the query that actually reaches the vectoriser; ``unknown`` is
        reported rather than dropped, so the UI can say why a skill was ignored.
        """
        if user_skills is None:
            return [], []
        if isinstance(user_skills, str):
            names = parse_skill_list(user_skills)
        else:
            names = []
            seen: set[str] = set()
            for item in user_skills:
                cleaned = " ".join(str(item).split())
                if not cleaned:
                    continue
                key = cleaned.casefold()
                if key in seen:
                    continue
                seen.add(key)
                names.append(cleaned)
        known: list[str] = []
        unknown: list[str] = []
        vocabulary = self._vectorizer.vocabulary_ if self._fitted else {}
        for name in names:
            (known if normalize_skill_name(name) in vocabulary else unknown).append(name)
        return known, unknown

    # -- scoring ---------------------------------------------------------------

    def similarity(self, user_skills: str | Sequence[str] | None) -> pd.Series:
        """Cosine similarity between the user and every role, as 0-1 floats.

        :returns: a Series indexed by role, in the profile order. An empty user
            skill list, or one containing no known skill, scores 0.0 everywhere -
            the query vector is all zeros and has no direction to compare.
        """
        if self.role_count == 0:
            return pd.Series(dtype="float64")

        query = build_user_document(user_skills)
        if not query:
            return pd.Series(0.0, index=pd.Index(self.roles, name="role"), dtype="float64")

        vector = self._vectorizer.transform([query])
        scores = cosine_similarity(vector, self._matrix).ravel()
        return pd.Series(scores, index=pd.Index(self.roles, name="role"), dtype="float64")

    def recommend(
        self,
        user_skills: str | Sequence[str] | None,
        top_n: int = DEFAULT_TOP_N,
    ) -> pd.DataFrame:
        """Rank roles by Skill Similarity Score and explain each one.

        :param user_skills: free text (``"Python, SQL, Pandas"``) or a list.
        :param top_n: how many roles to return, 1 or greater. Asking for more
            than there are roles returns them all rather than failing.
        :returns: a DataFrame with :data:`RECOMMENDATION_COLUMNS`, best first.
            Each row carries the matched, missing and required skill tuples, so a
            score can always be checked by hand, plus ``rule_based_pct`` - the
            plain set-arithmetic overlap - for comparison.

        Ties are broken alphabetically, so the ranking is stable across runs
        rather than depending on the order the database happened to return.
        An empty or entirely unknown skill list returns an empty frame: there is
        nothing to rank against, and inventing a ranking would be misleading.
        """
        top_n = _validate_top_n(top_n)
        if self.role_count == 0:
            return _empty_recommendations()

        document = build_user_document(user_skills)
        if not document:
            return _empty_recommendations()

        query = self._vectorizer.transform([document])
        # A query made only of out-of-vocabulary skills has an all-zero vector
        # and matches nothing, so there is no ranking to report.
        if query.nnz == 0:
            return _empty_recommendations()

        scores = cosine_similarity(query, self._matrix).ravel()
        ranked = pd.DataFrame(
            {
                "role": list(self.roles),
                "similarity": scores,
            }
        )
        ranked = ranked.sort_values(
            ["similarity", "role"], ascending=[False, True]
        ).reset_index(drop=True)

        required = dict(
            zip(self.role_profiles["role"], self.role_profiles["required_skills"])
        )
        # ``job_count`` is part of the build_role_profiles() layout, but a
        # hand-built fixture may omit it; a 0 default keeps ranking working.
        if "job_count" in self.role_profiles.columns:
            job_counts = dict(zip(self.role_profiles["role"], self.role_profiles["job_count"]))
        else:
            job_counts = {role: 0 for role in self.roles}

        rows: list[dict[str, object]] = []
        for role in ranked["role"].tolist()[:top_n]:
            needed = list(required[role])
            matched, missing = compare_skill_sets(needed, document)
            required_count = len(needed)
            rows.append(
                {
                    "role": role,
                    # Named a similarity, not a probability: cosine similarity
                    # is a geometric measure, not a forecast.
                    "score": round(float(ranked.loc[ranked["role"] == role, "similarity"].iloc[0]) * 100.0, 1),
                    "matched_skills": tuple(matched),
                    "missing_skills": tuple(missing),
                    "required_skills": tuple(needed),
                    "matched_count": len(matched),
                    "missing_count": len(missing),
                    "required_count": required_count,
                    # The transparent baseline, on the same matched/missing
                    # split, so the two numbers differ only in how they weigh
                    # the shared skills.
                    "rule_based_pct": round(
                        100.0 * len(matched) / required_count if required_count else 0.0, 1
                    ),
                    "job_count": int(job_counts[role]),
                }
            )

        return pd.DataFrame(rows, columns=list(RECOMMENDATION_COLUMNS))


def recommend_roles(
    user_skills: str | Sequence[str] | None,
    role_profiles: pd.DataFrame | None = None,
    top_n: int = DEFAULT_TOP_N,
) -> pd.DataFrame:
    """Rank job roles for one person, in a single call.

    The convenience wrapper for one-off use: it builds a
    :class:`RoleRecommender` and immediately asks it for recommendations. Hold a
    :class:`RoleRecommender` directly instead when scoring repeatedly, so the
    vectoriser is fitted once.

    :param user_skills: free text or a list of skill names.
    :param role_profiles: the role profiles to rank. Loaded from PostgreSQL by
        :func:`load_role_profiles` when omitted, so the caller usually does not
        pass this at all.
    :param top_n: how many roles to return.
    :returns: a DataFrame with :data:`RECOMMENDATION_COLUMNS`, best first.
    """
    if role_profiles is None:
        role_profiles = load_role_profiles()
    return RoleRecommender(role_profiles).recommend(user_skills, top_n=top_n)


#: Why a recommendation request produced no ranking. The UI switches on this
#: instead of re-deriving the conditions itself.
STATUS_OK = "ok"
STATUS_NO_ROLES = "no_roles"
STATUS_NO_SKILLS = "no_skills"
STATUS_NO_KNOWN_SKILLS = "no_known_skills"


def recommend_with_diagnostics(
    user_skills: str | Sequence[str] | None,
    role_profiles: pd.DataFrame | None = None,
    top_n: int = DEFAULT_TOP_N,
) -> dict[str, Any]:
    """Rank roles **and** explain why, so the caller never has to guess.

    ``recommend_roles`` returns only rows. On its own that is ambiguous: an
    empty result could mean the user typed nothing, typed only skills this
    market has never seen, or the profiles are empty. Each of those needs a
    different message, and none of them is an error, so the condition is
    reported rather than raised.

    :returns: a dict with

        * ``results`` - the DataFrame from :meth:`RoleRecommender.recommend`,
        * ``known`` / ``unknown`` - the typed skills that are, and are not, in
          the fitted vocabulary, each in the user's own spelling,
        * ``status`` - one of :data:`STATUS_OK`, :data:`STATUS_NO_ROLES`,
          :data:`STATUS_NO_SKILLS` or :data:`STATUS_NO_KNOWN_SKILLS`,
        * ``message`` - a ready-to-display sentence for the non-OK cases, and
        * ``info`` - the :func:`model_information` dict for the materialised
          recommender, so the UI's "how this works" panel never fits a second
          copy of the model.
    """
    if role_profiles is None:
        role_profiles = load_role_profiles()
    recommender = RoleRecommender(role_profiles)
    results = recommender.recommend(user_skills, top_n=top_n)
    known, unknown = recommender.split_known_skills(user_skills)

    if recommender.role_count == 0:
        status, message = STATUS_NO_ROLES, (
            "No job roles with recorded skills are available, so there is "
            "nothing to recommend yet."
        )
    elif not known:
        if recommender.vocabulary_size == 0:
            status, message = STATUS_NO_ROLES, (
                "The skill vocabulary is empty, so no similarity can be computed."
            )
        elif not build_user_document(user_skills):
            status, message = STATUS_NO_SKILLS, "Please enter at least one skill."
        else:
            status, message = STATUS_NO_KNOWN_SKILLS, (
                "None of the skills you listed appear in this job market's "
                "vocabulary, so there is nothing to compare. The market's "
                "known skills are listed below."
            )
    else:
        status, message = STATUS_OK, ""

    if not role_profiles.empty and "job_count" in role_profiles.columns:
        postings = int(role_profiles["job_count"].sum())
    else:
        postings = 0

    return {
        "results": results,
        "known": known,
        "unknown": unknown,
        "status": status,
        "message": message,
        "role_count": recommender.role_count,
        "vocabulary_size": recommender.vocabulary_size,
        "info": _model_information_for(recommender, postings),
    }


def load_role_profiles(
    links: pd.DataFrame | None = None,
    jobs: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build the role profiles this recommender needs, from PostgreSQL.

    This is the **only** place in the ML package that touches data sources, and
    it does not own a connection either: it calls the existing data layer,
    ``src.data.queries``, which owns every connection in the project. The skill
    requirements come from ``jobs -> job_skills -> skills``, so no job skill is
    hardcoded anywhere in the ML code.

    :param links: optional pre-loaded ``get_job_skill_links()`` output, to
        reuse a frame the dashboard has already cached instead of re-querying.
    :param jobs: optional pre-loaded ``get_all_jobs()`` output, for the titles.
    :returns: the output of :func:`ml.preprocessing.build_role_profiles`.
    """
    # Imported here, not at module scope, so the pure-logic half of this module
    # can be imported and tested without a database being reachable.
    from src.data import queries

    if links is None:
        links = queries.get_job_skill_links()
    if jobs is None:
        jobs = queries.get_all_jobs()
    return build_role_profiles(build_job_skill_documents(links, jobs))


def _model_information_for(
    recommender: RoleRecommender, postings: int
) -> dict[str, Any]:
    """Describe an already-fitted recommender for the "how this works" panel.

    Shared by :func:`model_information` and :func:`recommend_with_diagnostics`
    so the panel can be drawn from exactly the recommender that produced the
    visible ranking, without fitting a second copy.
    """
    return {
        "method": "TF-IDF over skill names + cosine similarity",
        "role_count": recommender.role_count,
        "vocabulary_size": recommender.vocabulary_size,
        "document_unit": "one advertised job role",
        "term_unit": "one skill name",
        "postings_represented": postings,
        "steps": (
            "1. Each job role is represented as the set of skills its postings require.",
            "2. TF-IDF turns each role's skills into a vector, giving rarer skills more weight.",
            "3. Your skills are turned into a vector using the same vocabulary and weights.",
            "4. Cosine similarity measures how closely the two vectors point the same way.",
            "5. Roles are ranked by that similarity, shown as a Skill Similarity Score out of 100.",
        ),
        # The counts above are real; the limitation text is worded so it stays
        # true whatever those counts turn out to be.
        "limitations": (
            f"It is currently fitted on {recommender.role_count} role profiles built from "
            f"{postings} postings, over a vocabulary of {recommender.vocabulary_size} "
            f"skills. {MODEL_LIMITATIONS}"
        ),
        "comparison": MODEL_COMPARISON,
        "no_external_services": (
            "Everything runs locally. No LLM, no embedding API, no external service "
            "is contacted, and scikit-learn is the only added dependency."
        ),
    }


def model_information(role_profiles: pd.DataFrame | None = None) -> dict[str, Any]:
    """Describe the fitted model, for the dashboard's "how this works" panel.

    :param role_profiles: the profiles to describe. Loaded from the database
        when omitted.
    :returns: a dict of plain values - role and vocabulary sizes, the number of
        postings behind them, the steps the method follows, the limitations, and
        the side-by-side comparison of the two scoring methods.

    Every figure here is counted from the data that was actually loaded, so the
    panel cannot claim a coverage the dataset does not have.
    """
    if role_profiles is None:
        role_profiles = load_role_profiles()
    recommender = RoleRecommender(role_profiles)
    if not role_profiles.empty and "job_count" in role_profiles.columns:
        postings = int(role_profiles["job_count"].sum())
    else:
        postings = 0
    return _model_information_for(recommender, postings)
