"""Skill normalisation and document building for the Role Recommendation Engine.

This module is the ML package's equivalent of the rule-based normalisation that
already exists in the Skill Gap Analyzer, and it is the **single source of
truth** for it: ``dashboard.components`` imports :func:`normalize_skill_name` and
:func:`parse_skill_list` from here rather than keeping a second copy. Both the
transparent rule-based baseline and the TF-IDF recommender therefore compare
skills under exactly the same rules, which is what makes the side-by-side
comparison in the dashboard meaningful.

Everything here is pure: pandas in, pandas out, no database and no scikit-learn
import. :mod:`ml.recommender` is the layer that turns these documents into
vectors.

What "normalisation" means here, and what it deliberately does not mean
--------------------------------------------------------------------
A skill is normalised by trimming its ends, collapsing runs of internal
whitespace to a single space, and case-folding. That is all.

* **No fuzzy matching.** ``"Pythonn"`` is not Python, and is reported as a skill
  the market has never seen.
* **No synonym expansion.** ``"PyTorch"`` and ``"TensorFlow"`` stay two
  different skills. A user who has one does not get credit for the other.
* **No stemming or lemmatisation.** ``"Spark"`` and ``"Apache Spark"`` are
  distinct terms, exactly as the database stores them.

These are not omissions. On a 32-skill vocabulary, guessing that two names mean
the same thing would invent a relationship the data does not contain, and the
whole point of this prototype is that every number can be explained.

Documents
---------
A *document* is a tuple of normalised skill names, and it is what gets turned
into a TF-IDF vector. Two levels are produced:

* one document per **job posting**, from its ``job_skills`` rows;
* one document per **role**, the union of the skills its postings require.

The role level is what gets ranked, so a role with four postings appears once
rather than four times. See :func:`build_role_profiles`.
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

import pandas as pd

#: Characters treated as separators in a free-text skill list. A comma is the
#: documented format; newline, semicolon and pipe are tolerated so a list pasted
#: from a resume still parses. "/" and "+" are deliberately NOT separators,
#: because real skill names contain them ("CI/CD", "C++").
SKILL_SEPARATOR_PATTERN = re.compile(r"[,;\n\r|]+")

#: Column layout of the frame returned by :func:`build_job_skill_documents`.
JOB_DOCUMENT_COLUMNS: tuple[str, ...] = (
    "job_id",
    "job_title",
    "skills",
    "document",
    "skill_count",
)

#: Column layout of the frame returned by :func:`build_role_profiles`.
ROLE_PROFILE_COLUMNS: tuple[str, ...] = (
    "role",
    "job_count",
    "required_skills",
    "required_count",
    "document",
    "skill_frequencies",
)


def normalize_skill_name(value: str) -> str:
    """Return the comparison form of one skill name.

    Trims the ends, collapses runs of internal whitespace to a single space and
    case-folds, so ``"  PyTorch "`` and ``"pytorch"`` are one skill. Case folding
    uses ``str.casefold()``, which handles non-ASCII letters more predictably
    than ``str.lower()``.

    :raises TypeError: if ``value`` is not a string.
    """
    if not isinstance(value, str):
        raise TypeError(f"skill name must be a str, got {type(value).__name__}.")
    return " ".join(value.split()).casefold()


def parse_skill_list(raw: str | None) -> list[str]:
    """Turn free text into a clean, de-duplicated list of skill names.

    ``"Python, SQL,  python ,Git"`` becomes ``["Python", "SQL", "Git"]``.

    * split on :data:`SKILL_SEPARATOR_PATTERN`,
    * strip each token and collapse its internal whitespace,
    * drop blanks, so a trailing comma is not an error,
    * remove duplicates **case-insensitively**, keeping the first spelling typed,
      and
    * preserve the order typed, so reports read in the user's own order.

    :raises TypeError: if ``raw`` is neither a string nor ``None``.
    """
    if raw is None:
        return []
    if not isinstance(raw, str):
        raise TypeError(f"raw skills must be a str or None, got {type(raw).__name__}.")

    seen: set[str] = set()
    skills: list[str] = []
    for token in SKILL_SEPARATOR_PATTERN.split(raw):
        cleaned = " ".join(token.split())
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        skills.append(cleaned)
    return skills


def build_user_document(user_skills: str | Sequence[str] | None) -> tuple[str, ...]:
    """Return the normalised skill tuple that represents a user.

    Accepts either free text (``"Python, SQL"``) or an already-split sequence,
    so callers holding a list do not have to re-join it into text. Either way
    the result is normalised and de-duplicated, which is what makes the query
    comparable with a document built from the database.
    """
    if user_skills is None:
        return ()
    if isinstance(user_skills, str):
        names = parse_skill_list(user_skills)
    else:
        names = [" ".join(str(item).split()) for item in user_skills]
        seen: set[str] = set()
        unique: list[str] = []
        for name in names:
            if not name:
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            unique.append(name)
        names = unique
    return tuple(normalize_skill_name(name) for name in names)


def _empty(columns: Iterable[str], dtypes: dict[str, str] | None = None) -> pd.DataFrame:
    """An empty frame carrying ``columns`` and the requested dtypes."""
    dtypes = dtypes or {}
    return pd.DataFrame(
        {column: pd.Series(dtype=dtypes.get(column, "object")) for column in columns}
    )


def build_job_skill_documents(
    links: pd.DataFrame,
    jobs: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Turn job <-> skill rows into one TF-IDF document per job posting.

    :param links: the flattened junction table, as returned by
        ``queries.get_job_skill_links()`` - columns ``job_id``, ``skill_id``,
        ``skill_name``, ``skill_category``.
    :param jobs: optional postings frame carrying ``job_id`` and ``job_title``.
        Without it the result has an empty ``job_title``, which is enough for
        ranking but not for a readable report.
    :returns: one row per ``job_id`` with ``job_id``, ``job_title``, ``skills``
        (the database's own spellings, alphabetically), ``document`` (the same
        names normalised, and the actual input to the vectoriser) and
        ``skill_count``.

    A skill that two rows of ``links`` both name for one job is stored once:
    ``job_skills`` has a composite primary key so that cannot happen in the
    database, but the recommender must not depend on that constraint holding.
    """
    empty = _empty(
        JOB_DOCUMENT_COLUMNS,
        {"skill_count": "int64"},
    )
    if links is None or links.empty:
        return empty
    if "skill_name" not in links.columns or "job_id" not in links.columns:
        raise ValueError("links must have 'job_id' and 'skill_name' columns.")

    frame = links.dropna(subset=["skill_name"]).copy()
    if frame.empty:
        return empty

    titles: dict[Any, str] = {}
    if jobs is not None and not jobs.empty and "job_title" in getattr(jobs, "columns", []):
        titles = dict(zip(jobs["job_id"], jobs["job_title"]))

    rows: list[dict[str, object]] = []
    for job_id, group in frame.groupby("job_id", sort=True):
        # A set keyed on the normalised name: "Python" and "python" from two
        # different rows collapse, while the first spelling seen is kept.
        canonical: dict[str, str] = {}
        for name in group["skill_name"]:
            cleaned = " ".join(str(name).split())
            if not cleaned:
                continue
            canonical.setdefault(normalize_skill_name(cleaned), cleaned)
        if not canonical:
            continue
        skills = tuple(sorted(canonical.values(), key=lambda value: (value.casefold(), value)))
        rows.append(
            {
                "job_id": job_id,
                "job_title": str(titles.get(job_id, "")) or "Unknown Role",
                "skills": skills,
                "document": tuple(normalize_skill_name(name) for name in skills),
                "skill_count": len(skills),
            }
        )

    if not rows:
        return empty
    return pd.DataFrame(rows, columns=list(JOB_DOCUMENT_COLUMNS)).sort_values(
        "job_id"
    ).reset_index(drop=True)


def build_role_profiles(job_documents: pd.DataFrame) -> pd.DataFrame:
    """Aggregate posting-level documents into one profile per job role.

    :param job_documents: the output of :func:`build_job_skill_documents`.
    :returns: one row per ``role`` with

        * ``role`` - the advertised job title,
        * ``job_count`` - how many postings advertise it,
        * ``required_skills`` - the union of their skills, **most frequently
          required first, then alphabetically**, so a report reads from the
          skill the role always wants down to the one only one posting mentions,
        * ``required_count`` - how many distinct skills that is,
        * ``document`` - the same skills normalised, the actual input to the
          vectoriser, and
        * ``skill_frequencies`` - ``{normalised skill: postings requiring it}``,
          which is what orders ``required_skills``.

    This aggregation is the answer to "several postings share one role". The
    alternative - ranking postings and repeating the role - would fill the top
    five with the same title, and would silently favour whichever role happened
    to post most often. The union is a fair, visible, one-line rule: *a role is
    represented by every skill any of its postings asks for*.

    Roles whose postings carry no skills at all are dropped rather than
    represented as empty documents, because an empty document has no direction
    and would score 0 against everything.
    """
    empty = _empty(
        ROLE_PROFILE_COLUMNS,
        {"job_count": "int64", "required_count": "int64"},
    )
    if job_documents is None or job_documents.empty:
        return empty
    if "job_title" not in job_documents.columns or "document" not in job_documents.columns:
        raise ValueError("job documents must have 'job_title' and 'document' columns.")

    rows: list[dict[str, object]] = []
    for role, group in job_documents.groupby("job_title", sort=True):
        frequencies: dict[str, int] = {}
        # 'document' is the normalised form and 'skills' the database's own
        # spelling, aligned element for element by build_job_skill_documents().
        # The display form is therefore recoverable exactly, not guessed at.
        display: dict[str, str] = {}
        for document, skills in zip(group["document"], group["skills"]):
            for name, canonical in zip(document, skills):
                frequencies[name] = frequencies.get(name, 0) + 1
                display.setdefault(name, canonical)
        if not frequencies:
            continue

        ordered = sorted(
            frequencies, key=lambda name: (-frequencies[name], display[name].casefold())
        )
        rows.append(
            {
                "role": str(role),
                "job_count": int(len(group)),
                "required_skills": tuple(display[name] for name in ordered),
                "required_count": len(ordered),
                "document": tuple(ordered),
                "skill_frequencies": frequencies,
            }
        )

    if not rows:
        return empty
    return pd.DataFrame(rows, columns=list(ROLE_PROFILE_COLUMNS)).sort_values(
        ["required_count", "role"], ascending=[False, True]
    ).reset_index(drop=True)


def compare_skill_sets(
    required: Sequence[str], user: Sequence[str]
) -> tuple[list[str], list[str]]:
    """Split a role's requirements into the ones held and the ones not held.

    :returns: ``(matched, missing)``, both in the order ``required`` was given,
        with the database's spelling preserved on both sides.

    This is the rule-based overlap - plain set arithmetic on normalised names.
    It is the baseline the TF-IDF score is shown next to, and it is deliberately
    the simplest thing that could possibly work.
    """
    required_names = list(required)
    user_keys = {normalize_skill_name(name) for name in user}
    matched: list[str] = []
    missing: list[str] = []
    for name in required_names:
        if normalize_skill_name(name) in user_keys:
            matched.append(str(name))
        else:
            missing.append(str(name))
    return matched, missing
