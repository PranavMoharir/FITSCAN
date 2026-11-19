"""The ranking order of stored matches and its tie-breakers (LLD §7.10, HLD §10.7).

    1. score              descending, full precision (never the rounded display value)
    2. text_similarity    descending: TF-IDF tie-breaker, only decides between exactly equal scores
    3. required ratio     descending, from score_breakdown
    4. the other side's ID ascending, so the order is always the same

`services/matches.py` uses the SQL form; `rank_key` is the same order in Python, used by the
tests and the manual check. The ranks shown by the API are assigned after this ordering, and
rounding for display happens after that, so rounding can never change a rank.

No scikit-learn here: the API imports this module.
"""

import math
import uuid

from sqlalchemy import Double

from app.models import Match

# score_breakdown -> 'required' ->> 'ratio', as a number
REQUIRED_RATIO = Match.score_breakdown[("required", "ratio")].astext.cast(Double)


def jobs_for_candidate_order() -> tuple:
    """ORDER BY for the top jobs of one candidate."""
    return (Match.score.desc(), Match.text_similarity.desc().nulls_last(), REQUIRED_RATIO.desc().nulls_last(),
            Match.job_id.asc())


def candidates_for_job_order() -> tuple:
    """ORDER BY for the top candidates of one job."""
    return (Match.score.desc(), Match.text_similarity.desc().nulls_last(), REQUIRED_RATIO.desc().nulls_last(),
            Match.candidate_id.asc())


def rank_key(score: float, text_similarity: float | None, required_ratio: float | None, other_id: uuid.UUID) -> tuple:
    """Sort key with the same order as the SQL above (missing values last, as in PostgreSQL).

    PostgreSQL orders UUIDs by their bytes, which is the order of `uuid.UUID` values in Python.
    """
    def descending(value: float | None) -> tuple:
        return (1, 0.0) if value is None else (0, -value)

    if math.isnan(score):
        raise ValueError("a score is never NaN")
    return (-score, *descending(text_similarity), *descending(required_ratio), other_id)
