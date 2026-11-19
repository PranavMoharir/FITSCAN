"""Ranking order, the TF-IDF tie-breaker and scoring one candidate against all jobs (LLD §7.6-7.10). Offline.

The four score-precision tests of LLD §9.7 are here in their Python form; the same order is
checked against PostgreSQL through the API in tests/integration/test_match_flow.py.
"""

import uuid
from decimal import Decimal
from fractions import Fraction

from app.matching import explanation
from app.matching.engine import CandidateInput, JobInput, score_candidate
from app.matching.ranking import rank_key
from app.matching.scoring import BASELINE_WEIGHTS, CandidateProfile, JobProfile
from app.matching.tfidf import TextSimilarity

S = frozenset
IDS = [uuid.UUID(int=n) for n in range(1, 20)]


def ranked(rows):
    """rows: (score, text_similarity, required_ratio, id) -> ids in rank order."""
    return [row[3] for row in sorted(rows, key=lambda row: rank_key(*row))]


# --- Score-precision tests (LLD §9.7) ----------------------------------------------------------------


def test_1_different_scores_that_display_the_same_keep_their_order():
    """80.004 and 80.001 both display as 80.00; 80.004 ranks first even with the lower similarity."""
    rows = [(80.001, 0.90, 1.0, IDS[0]), (80.004, 0.10, 1.0, IDS[1])]
    assert explanation.display(80.004) == explanation.display(80.001) == 80.0
    assert ranked(rows) == [IDS[1], IDS[0]]


def test_2_top_10_boundary_uses_full_precision():
    """11 matches; the 10th and 11th differ only after the second decimal place."""
    rows = [(90.0 - n, 0.5, 1.0, IDS[n]) for n in range(9)]       # 90 ... 82
    rows += [(50.001, 0.99, 1.0, IDS[9]), (50.004, 0.01, 1.0, IDS[10])]
    top_10 = ranked(rows)[:10]
    assert IDS[10] in top_10 and IDS[9] not in top_10


def test_3_equal_scores_from_different_components_go_to_the_tie_breaker():
    """Both pairs score exactly 71 2/3 (stored identically), so text similarity decides."""
    worked = JobInput(IDS[0], JobProfile(S({"Python", "FastAPI", "PostgreSQL", "Docker"}), S({"Redis", "Kubernetes"}),
                                         Decimal(3), "Pune, India", False), "python fastapi")
    second = JobInput(IDS[1], JobProfile(S({"Python", "FastAPI", "Kafka"}), S(), None, "Mumbai", False), "python")
    person = CandidateInput(IDS[5], CandidateProfile(S({"Python", "FastAPI", "PostgreSQL", "Redis", "Git"}),
                                                     Decimal(2), "Pune"), "python")
    rows = score_candidate(person, [worked, second], [0.2, 0.7], BASELINE_WEIGHTS)
    assert rows[0].score == rows[1].score == 71.66666666666667
    keyed = [(r.score, r.text_similarity, r.score_breakdown["required"]["ratio"], r.job_id) for r in rows]
    assert ranked(keyed) == [IDS[1], IDS[0]]  # higher text similarity first


def test_4_stored_versus_shown():
    """The stored score is unrounded; the explanation shows exactly 2 decimals."""
    job = JobInput(IDS[0], JobProfile(S({"Python", "Docker", "AWS"}), S(), None, "Pune", False), None)
    person = CandidateInput(IDS[1], CandidateProfile(S({"Python"}), None, "Pune"), None)
    row = score_candidate(person, [job], [0.0], BASELINE_WEIGHTS)[0]
    assert row.score == float(Fraction(160, 3)) == 53.333333333333336  # exactly 160/3, converted once
    assert 70 / 3 + 15 + 10 + 5 == 53.33333333333333  # plain floats would store a different value
    assert explanation.display(row.score) == 53.33
    assert row.explanation.startswith("Score 53.33/100.")


def test_tie_breakers_in_order():
    same = 60.0
    rows = [
        (same, 0.30, 0.5, IDS[3]),
        (same, 0.30, 1.0, IDS[2]),   # same similarity: higher required ratio first
        (same, 0.40, 0.0, IDS[4]),   # higher similarity first
        (same, 0.30, 1.0, IDS[1]),   # everything equal: lower ID first
        (same, None, 1.0, IDS[0]),   # no similarity: last, as NULLS LAST in SQL
    ]
    assert ranked(rows) == [IDS[4], IDS[1], IDS[2], IDS[3], IDS[0]]


# --- TF-IDF tie-breaker ------------------------------------------------------------------------------


def test_text_similarity_prefers_related_texts():
    jobs = ["Backend developer: Python, Django and PostgreSQL APIs", "Registered nurse for the night shift in a hospital"]
    resumes = ["Python developer building Django REST APIs on PostgreSQL"]
    similarity = TextSimilarity(jobs, resumes).for_candidate(0)
    assert similarity[0] > similarity[1] >= 0
    assert all(0 <= value <= 1 for value in similarity)


def test_text_similarity_handles_missing_texts():
    similarity = TextSimilarity(["Python developer", None, ""], [None, "python"])
    assert similarity.for_candidate(0) == [0.0, 0.0, 0.0]
    assert similarity.for_candidate(1)[0] > 0 and similarity.for_candidate(1)[1:] == [0.0, 0.0]


def test_text_similarity_with_no_usable_words_at_all():
    similarity = TextSimilarity(["", None, "the and of"], ["", "a"])  # only stop words: empty vocabulary
    assert similarity.vocabulary_size == 0
    assert similarity.for_candidate(1) == [0.0, 0.0, 0.0]


def test_text_similarity_is_deterministic():
    jobs = ["Data engineer with Spark and Airflow", "Frontend developer, React and TypeScript"]
    resumes = ["Spark pipelines and Airflow DAGs", "React, TypeScript, CSS"]
    first = [TextSimilarity(jobs, resumes).for_candidate(i) for i in range(2)]
    second = [TextSimilarity(jobs, resumes).for_candidate(i) for i in range(2)]
    assert first == second


def test_text_similarity_never_changes_the_score():
    job = JobInput(IDS[0], JobProfile(S({"Python"}), S(), None, "Pune", False), "python")
    person = CandidateInput(IDS[1], CandidateProfile(S({"Python"}), None, "Pune"), "python")
    low = score_candidate(person, [job], [0.0], BASELINE_WEIGHTS)[0]
    high = score_candidate(person, [job], [1.0], BASELINE_WEIGHTS)[0]
    assert low.score == high.score == 100.0
    assert low.explanation == high.explanation


# --- One candidate against every job -----------------------------------------------------------------


def test_score_candidate_makes_one_row_per_job():
    jobs = [JobInput(IDS[n], JobProfile(S({"Python"}) if n % 2 else S(), S(), None, "Pune", False), None)
            for n in range(5)]
    person = CandidateInput(IDS[9], CandidateProfile(S({"Python"}), None, "Pune"), None)
    rows = score_candidate(person, jobs, [0.0] * 5, BASELINE_WEIGHTS)
    assert [row.job_id for row in rows] == IDS[:5]
    assert {row.candidate_id for row in rows} == {IDS[9]}
    assert [row.score for row in rows] == [15.0, 100.0, 15.0, 100.0, 15.0]  # O2 jobs score at most 15
