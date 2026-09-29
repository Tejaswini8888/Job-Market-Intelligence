"""Machine-learning layer for the Job Market Intelligence platform.

Two modules, deliberately separated by responsibility:

* :mod:`ml.preprocessing` - normalise skill names, deduplicate them, and turn
  ``jobs -> job_skills -> skills`` into one text document per posting and one
  profile per job role. Pure pandas: no database, no scikit-learn.
* :mod:`ml.recommender` - TF-IDF vectors and cosine similarity over those role
  profiles, returning ranked role recommendations with a Skill Similarity
  Score. This is the project's only scikit-learn user.

The layer is a **prototype**, not a trained or validated model. It runs on a
small synthetic dataset and every number it produces is explainable by
arithmetic. The transparent, rule-based Skill Gap Analyzer is *not* replaced by
it: the two are shown side by side, because they answer different questions.

Typical use::

    from ml.recommender import recommend_roles

    results = recommend_roles("Python, SQL, Pandas, Git, Docker", top_n=5)
    results[["role", "score", "rule_based_pct"]]

See :data:`ml.recommender.MODEL_LIMITATIONS` for what this cannot tell you.
"""

from __future__ import annotations

from ml.preprocessing import (
    build_job_skill_documents,
    build_role_profiles,
    build_user_document,
    compare_skill_sets,
    normalize_skill_name,
    parse_skill_list,
)
from ml.recommender import (
    DEFAULT_TOP_N,
    MODEL_COMPARISON,
    MODEL_LIMITATIONS,
    RECOMMENDATION_COLUMNS,
    RoleRecommender,
    load_role_profiles,
    model_information,
    recommend_roles,
)

__all__ = [
    # preprocessing.py
    "build_job_skill_documents",
    "build_role_profiles",
    "build_user_document",
    "compare_skill_sets",
    "normalize_skill_name",
    "parse_skill_list",
    # recommender.py
    "DEFAULT_TOP_N",
    "MODEL_COMPARISON",
    "MODEL_LIMITATIONS",
    "RECOMMENDATION_COLUMNS",
    "RoleRecommender",
    "load_role_profiles",
    "model_information",
    "recommend_roles",
]
