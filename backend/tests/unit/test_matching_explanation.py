"""Matched and missing skills, the breakdown, the explanation sentence and display rounding (LLD §7.7). Offline."""

import re
from decimal import Decimal

import pytest

from app.matching import explanation, scoring
from app.matching.scoring import CandidateProfile, JobProfile, score_pair

S = frozenset
WORKED_SENTENCE = ("Score 71.67/100. Has 3 of 4 required skills (52.50 pts; missing Docker). Has 1 of 2 nice-to-have "
                   "skills (7.50 pts; missing Kubernetes). 2 years of experience against a 3-year minimum (6.67 pts). "
                   "Same city, Pune (5.00 pts).")


def explained(job: JobProfile, cand: CandidateProfile):
    result = score_pair(job, cand)
    score = float(result.score)
    matched, missing = explanation.skill_lists(result)
    parts = explanation.breakdown(result)
    return score, matched, missing, parts, explanation.explain(score, parts, missing)


def job(required=(), nice=(), minimum=None, location="Pune, India", remote=False) -> JobProfile:
    return JobProfile(S(required), S(nice), None if minimum is None else Decimal(str(minimum)), location, remote)


def candidate(skills=(), years=None, city="Pune") -> CandidateProfile:
    return CandidateProfile(S(skills), None if years is None else Decimal(str(years)), city)


WORKED = (job(["Python", "FastAPI", "PostgreSQL", "Docker"], ["Redis", "Kubernetes"], 3, "Pune, India"),
          candidate(["Python", "FastAPI", "PostgreSQL", "Redis", "Git"], 2, "Pune"))


def test_worked_example_sentence_is_exactly_the_documented_one():
    """LLD §7.7 / HLD §10.8."""
    assert explained(*WORKED)[4] == WORKED_SENTENCE


def test_matched_and_missing_skills_with_levels():
    _, matched, missing, _, _ = explained(*WORKED)
    assert matched == [{"skill": "FastAPI", "level": "required"}, {"skill": "PostgreSQL", "level": "required"},
                       {"skill": "Python", "level": "required"}, {"skill": "Redis", "level": "nice_to_have"}]
    assert missing == [{"skill": "Docker", "level": "required"}, {"skill": "Kubernetes", "level": "nice_to_have"}]


def test_breakdown_shape_and_full_precision():
    """LLD §3.3: counts, ratios and points of all four components, unrounded."""
    _, _, _, parts, _ = explained(*WORKED)
    assert parts["required"] == {"matched": 3, "total": 4, "ratio": 0.75, "points": 52.5, "rule": "ratio"}
    assert parts["nice_to_have"] == {"matched": 1, "total": 2, "ratio": 0.5, "points": 7.5, "rule": "ratio"}
    assert parts["experience"] == {"candidate_years": 2, "minimum": 3, "fit": 2 / 3, "points": 20 / 3, "rule": "ratio"}
    assert parts["location"] == {"candidate_city": "Pune", "job_location": "Pune, India", "job_city": "Pune",
                                 "fit": 1.0, "points": 5.0, "rule": "same_city"}


def test_display_breakdown_rounds_only_for_display():
    _, _, _, parts, _ = explained(*WORKED)
    shown = explanation.display_breakdown(parts)
    assert shown["experience"]["fit"] == 0.667 and shown["experience"]["points"] == 6.67
    assert parts["experience"]["points"] == 20 / 3  # the stored value is untouched


@pytest.mark.parametrize(
    ("value", "shown"),
    [(71.66666666666667, 71.67), (80.004, 80.0), (80.005, 80.01), (2.675, 2.68), (4.375, 4.38), (0.0, 0.0),
     (100.0, 100.0), (None, None)],
)
def test_display_rounds_half_up_on_the_decimal_value(value, shown):
    """2.675 as a float is slightly below 2.675; display rounds the number as written, half up."""
    assert explanation.display(value) == shown


def test_o2_job_explanation():
    score, matched, missing, parts, text = explained(job([], [], None, "Pune"), candidate(["Python"], 4, "Pune"))
    assert score == 15.0
    assert matched == missing == []
    assert text == ("Score 15.00/100. No required or nice-to-have skills could be identified for this job, so it gets "
                    "no skill points (0.00 pts). No minimum experience required (10.00 pts). Same city, Pune (5.00 pts).")


def test_no_nice_to_have_list_explanation():
    text = explained(job(["Python", "Docker"], [], 2, "Mumbai"), candidate(["Python"], 2, "Pune"))[4]
    assert text == ("Score 60.00/100. Has 1 of 2 required skills (35.00 pts; missing Docker). The job lists no "
                    "nice-to-have skills (15.00 pts). 2 years of experience against a 2-year minimum (10.00 pts). "
                    "Different city: candidate in Pune, job in Mumbai (0.00 pts).")


def test_no_required_but_nice_to_have_explanation():
    text = explained(job([], ["Redis", "Kafka"]), candidate(["Kafka"]))[4]
    assert "No required skills could be identified for this job (0.00 pts)." in text
    assert "Has 1 of 2 nice-to-have skills (7.50 pts; missing Redis)." in text


def test_unknown_experience_and_city_explanation():
    text = explained(job(["Python"], ["Redis"], 3, "Pune"), candidate(["Python", "Redis"], None, None))[4]
    assert "Experience not found in resume; the job asks for at least 3 years (0.00 pts)." in text
    assert "Candidate's city not found in resume (0.00 pts)." in text
    assert "Has 1 of 1 required skill (70.00 pts)." in text  # all matched: nothing missing to list


def test_remote_and_missing_job_location_explanations():
    assert "Remote job (5.00 pts)." in explained(job(["Python"], location="Remote", remote=True), candidate(["Python"]))[4]
    assert "Job location not given (0.00 pts)." in explained(job(["Python"], location=None), candidate(["Python"]))[4]


def test_singular_and_decimal_years():
    text = explained(job(["Python"], [], 1), candidate(["Python"], 0.5))[4]
    assert "0.5 years of experience against a 1-year minimum (5.00 pts)." in text
    text = explained(job(["Python"], [], 2.5), candidate(["Python"], 1))[4]
    assert "1 year of experience against a 2.5-year minimum (4.00 pts)." in text
    assert "at least 1 year (0.00 pts)" in explained(job(["Python"], [], 1), candidate(["Python"], None))[4]


def test_bangalore_bengaluru_explanation_names_the_canonical_city():
    text = explained(job(["Python"], location="Bangalore, Karnataka"), candidate(["Python"], city="Bengaluru"))[4]
    assert "Same city, Bengaluru (5.00 pts)." in text


CASES = [
    WORKED,
    (job([], [], None, "Pune"), candidate(["Python"], 4, "Pune")),
    (job(["Python", "Docker", "AWS"], ["Redis"], 4, "Mumbai"), candidate(["Python"], 1.5, "Pune")),
    (job([], ["Redis"], 2, None), candidate([], None, None)),
    (job(["Go"], [], None, "Remote", True), candidate(["Go"], 10, "Delhi")),
    (job(["Java", "Kafka", "Spring Boot"], ["AWS", "Docker", "Kubernetes"], 5, "Bengaluru"),
     candidate(["Java", "Docker"], 3, "Bangalore")),
]


@pytest.mark.parametrize(("job_profile", "cand"), CASES)
def test_explanation_agrees_with_the_breakdown(job_profile, cand):
    """Every number in the sentence is the display value of the stored score or a stored component."""
    score, _, missing, parts, text = explained(job_profile, cand)
    assert text.startswith(f"Score {explanation.display(score):.2f}/100.")
    shown_points = [float(value) for value in re.findall(r"\(([\d.]+) pts", text)]
    if parts["required"]["rule"] == scoring.NO_SKILLS_IDENTIFIED:
        expected = [parts["required"]["points"] + parts["nice_to_have"]["points"]]
    else:
        expected = [parts["required"]["points"], parts["nice_to_have"]["points"]]
    expected += [parts["experience"]["points"], parts["location"]["points"]]
    assert shown_points == [explanation.display(value) for value in expected]
    for item in missing:
        assert item["skill"] in text
    assert abs(score - sum(part["points"] for part in parts.values())) < 1e-9
