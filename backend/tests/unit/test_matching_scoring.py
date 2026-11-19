"""The scoring formula and its edge cases, computed exactly (LLD §7.4-7.6, §7.11; ADR-016, ADR-017). Offline."""

from decimal import Decimal
from fractions import Fraction

import pytest

from app.config import MatchWeights
from app.matching import scoring
from app.matching.scoring import BASELINE_WEIGHTS, CandidateProfile, JobProfile, Weights, city_of, score_pair

S = frozenset


def job(required=(), nice=(), minimum=None, location="Pune, India", remote=False) -> JobProfile:
    return JobProfile(S(required), S(nice), None if minimum is None else Decimal(str(minimum)), location, remote)


def candidate(skills=(), years=None, city="Pune") -> CandidateProfile:
    return CandidateProfile(S(skills), None if years is None else Decimal(str(years)), city)


WORKED_JOB = job(["Python", "FastAPI", "PostgreSQL", "Docker"], ["Redis", "Kubernetes"], 3, "Pune, India")
WORKED_CANDIDATE = candidate(["Python", "FastAPI", "PostgreSQL", "Redis", "Git"], 2, "Pune")


# --- The worked example and the formula ---------------------------------------------------------


def test_worked_example_is_exact():
    """LLD §7.11: 52.5 + 7.5 + 6.667 + 5 = exactly 215/3, stored as 71.66666666666667."""
    result = score_pair(WORKED_JOB, WORKED_CANDIDATE)
    assert result.score == Fraction(215, 3)
    assert float(result.score) == 71.66666666666667
    assert (result.required.points, result.nice_to_have.points) == (Fraction(105, 2), Fraction(15, 2))
    assert result.experience.points == Fraction(20, 3)
    assert result.location.points == 5
    assert result.required.matched == ("FastAPI", "PostgreSQL", "Python")
    assert result.required.missing == ("Docker",)
    assert result.nice_to_have.matched == ("Redis",)
    assert result.nice_to_have.missing == ("Kubernetes",)


def test_full_match_scores_100():
    result = score_pair(job(["Python", "Docker"], ["Redis"], 3), candidate(["Python", "Docker", "Redis"], 5))
    assert result.score == 100
    assert result.required.fit == result.nice_to_have.fit == result.experience.fit == result.location.fit == 1


def test_partial_required_match():
    result = score_pair(job(["Python", "Docker", "AWS"], ["Redis"]), candidate(["Python", "Redis"]))
    assert result.required.fit == Fraction(1, 3)
    assert result.required.points == Fraction(70, 3)
    assert result.required.missing == ("AWS", "Docker")
    assert result.score == Fraction(70, 3) + 15 + 10 + 5


def test_no_required_skill_matched():
    result = score_pair(job(["Java", "Spring Boot"], ["Kafka"], location="Mumbai"), candidate(["Python"]))
    assert result.required.fit == 0 and result.required.points == 0
    assert result.required.rule == scoring.RATIO
    assert result.required.missing == ("Java", "Spring Boot")
    assert result.score == 0 + 0 + 10 + 0


def test_nice_to_have_ratio():
    result = score_pair(job(["Python"], ["Redis", "Kubernetes", "AWS", "Terraform"]), candidate(["Python", "Redis"]))
    assert result.nice_to_have.fit == Fraction(1, 4)
    assert result.nice_to_have.points == Fraction(15, 4)
    assert result.nice_to_have.rule == scoring.RATIO


def test_candidate_skills_the_job_does_not_mention_change_nothing():
    plain = score_pair(job(["Python"], ["Redis"]), candidate(["Python"]))
    extra = score_pair(job(["Python"], ["Redis"]), candidate(["Python", "Rust", "Go", "Excel"]))
    assert plain == extra


def test_duplicate_skills_count_once():
    """Skills are sets: listing a skill twice cannot change a ratio."""
    profile = JobProfile(frozenset(["Python", "Python", "Docker"]), frozenset(), None, "Pune", False)
    result = score_pair(profile, CandidateProfile(frozenset(["Python", "Python"]), None, "Pune"))
    assert result.required.total == 2
    assert result.required.fit == Fraction(1, 2)


# --- Skill edge cases, including the O2 decision -------------------------------------------------


def test_required_skills_but_no_nice_to_have_list_gives_n_1():
    result = score_pair(job(["Python", "Docker"], []), candidate(["Python"]))
    assert result.nice_to_have.fit == 1
    assert result.nice_to_have.points == 15
    assert result.nice_to_have.rule == scoring.NONE_LISTED
    assert result.required.fit == Fraction(1, 2)


def test_job_with_no_skills_at_all_gives_r_0_and_n_0():
    """O2: no required and no nice-to-have skills -> R = 0 and N = 0, at most 15 points."""
    best_case = score_pair(job([], [], None, "Pune", remote=False), candidate(["Python", "Docker"], 10, "Pune"))
    assert best_case.required.fit == 0 and best_case.nice_to_have.fit == 0
    assert best_case.required.rule == best_case.nice_to_have.rule == scoring.NO_SKILLS_IDENTIFIED
    assert best_case.score == 15  # E = 1 and L = 1 are the only points left
    assert best_case.required.total == best_case.nice_to_have.total == 0


def test_job_with_no_skills_scores_below_any_partial_skill_match():
    """The reason for O2: an empty job no longer outranks a real partial match."""
    empty = score_pair(job([], [], None, "Pune"), candidate(["Python"], 5, "Pune"))
    partial = score_pair(job(["Python", "Docker", "AWS", "Go"], ["Redis", "Kafka"], 5, "Mumbai"),
                         candidate(["Python"], 5, "Pune"))
    assert partial.score == Fraction(35, 2) + 0 + 10 + 0  # 27.5
    assert empty.score < partial.score


def test_no_required_but_nice_to_have_skills_keeps_the_approved_rules():
    """Unchanged by O2: R = 0 (flagged) and N is the usual ratio."""
    result = score_pair(job([], ["Redis", "Kafka"]), candidate(["Redis"]))
    assert result.required.fit == 0
    assert result.required.rule == scoring.NO_REQUIRED_IDENTIFIED
    assert result.nice_to_have.fit == Fraction(1, 2)
    assert result.nice_to_have.rule == scoring.RATIO
    assert result.score == 0 + Fraction(15, 2) + 10 + 5


def test_candidate_without_skills():
    """LLD §7.5: R = 0; N = 0 unless the job has no nice-to-have list."""
    with_nice = score_pair(job(["Python"], ["Redis"]), candidate([]))
    without_nice = score_pair(job(["Python"], []), candidate([]))
    assert (with_nice.required.fit, with_nice.nice_to_have.fit) == (0, 0)
    assert (without_nice.required.fit, without_nice.nice_to_have.fit) == (0, 1)


# --- Experience ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("minimum", "years", "fit", "rule"),
    [
        (3, 3, Fraction(1), scoring.RATIO),            # exactly the minimum
        (3, 7, Fraction(1), scoring.RATIO),            # above: capped at 1
        (3, 2, Fraction(2, 3), scoring.RATIO),         # below: linear
        (4, 1.5, Fraction(3, 8), scoring.RATIO),       # decimals stay exact
        (2.5, 1, Fraction(2, 5), scoring.RATIO),
        (3, 0, Fraction(0), scoring.RATIO),            # a known 0 years
        (None, 2, Fraction(1), scoring.NO_MINIMUM),    # no minimum
        (0, None, Fraction(1), scoring.NO_MINIMUM),    # a minimum of 0 is no minimum
        (None, None, Fraction(1), scoring.NO_MINIMUM),
        (3, None, Fraction(0), scoring.YEARS_UNKNOWN),  # minimum set, years not in the resume
    ],
)
def test_experience_fit(minimum, years, fit, rule):
    result = score_pair(job(["Python"], [], minimum), candidate(["Python"], years))
    assert result.experience.fit == fit
    assert result.experience.points == 10 * fit
    assert result.experience.rule == rule


# --- Location --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("job_location", "remote", "candidate_city", "fit", "rule"),
    [
        ("Pune, Maharashtra, India", False, "Pune", 1, scoring.SAME_CITY),
        ("pune", False, "Pune", 1, scoring.SAME_CITY),                       # case-insensitive
        ("  Pune ,  India", False, "Pune", 1, scoring.SAME_CITY),            # spaces
        ("Bangalore, Karnataka", False, "Bengaluru", 1, scoring.SAME_CITY),  # other spelling
        ("Bengaluru", False, "Bangalore", 1, scoring.SAME_CITY),
        ("Bombay", False, "Mumbai", 1, scoring.SAME_CITY),
        ("Mumbai, India", False, "Pune", 0, scoring.DIFFERENT_CITY),
        ("Navi Mumbai", False, "Mumbai", 0, scoring.DIFFERENT_CITY),          # a different city, not a prefix match
        ("Remote", True, "Pune", 1, scoring.REMOTE),
        ("Mumbai, India", True, None, 1, scoring.REMOTE),                    # remote: the city does not matter
        ("Hybrid - Pune", False, "Mumbai", 0, scoring.DIFFERENT_CITY),       # hybrid counts as city-based
        ("Pune, India", False, None, 0, scoring.CANDIDATE_CITY_UNKNOWN),
        (None, False, "Pune", 0, scoring.JOB_CITY_UNKNOWN),
        ("   ", False, "Pune", 0, scoring.JOB_CITY_UNKNOWN),
        # Cities that are not in app/locations/cities.json: the city part is compared as text.
        ("Stewartbury, AA", False, "Stewartbury", 1, scoring.SAME_CITY),
        ("Stewartbury, AA", False, "Pune", 0, scoring.DIFFERENT_CITY),
        ("Port Ericaburgh, AA", False, "port ericaburgh", 1, scoring.SAME_CITY),
    ],
)
def test_location_fit(job_location, remote, candidate_city, fit, rule):
    result = score_pair(job(["Python"], [], None, job_location, remote), candidate(["Python"], None, candidate_city))
    assert result.location.fit == fit
    assert result.location.points == 5 * fit
    assert result.location.rule == rule


def test_city_of_uses_the_shared_normalizer():
    assert city_of("Bangalore, Karnataka, India") == "Bengaluru"
    assert city_of("Gurgaon") == city_of("Gurugram")
    assert city_of("Christopherville, AA") == "Christopherville"
    assert city_of(None) is None and city_of(" , India") is None


# --- Bounds, weights and precision ------------------------------------------------------------------


def test_score_is_always_between_0_and_100():
    worst = score_pair(job(["Java"], ["Kafka"], 5, "Mumbai"), candidate([], None, None))
    best = score_pair(job(["Java"], ["Kafka"], 5, "Mumbai"), candidate(["Java", "Kafka"], 9, "Mumbai"))
    assert worst.score == 0
    assert best.score == 100


def test_clamp_is_a_guard():
    assert scoring.clamp(Fraction(-1, 10**9)) == 0
    assert scoring.clamp(Fraction(100) + Fraction(1, 10**9)) == 100
    assert scoring.clamp(Fraction(215, 3)) == Fraction(215, 3)


def test_weights_from_settings_are_exact():
    weights = Weights.from_settings(MatchWeights(required=70, nice=15, experience=10, location=5))
    assert weights == BASELINE_WEIGHTS
    odd = Weights.from_settings(MatchWeights(required=33.3, nice=33.3, experience=33.4, location=0))
    assert odd.required == Fraction(333, 10)
    assert odd.total == 100


def test_configured_weights_are_used():
    weights = Weights.from_settings(MatchWeights(required=50, nice=20, experience=20, location=10))
    result = score_pair(WORKED_JOB, WORKED_CANDIDATE, weights)
    assert result.score == 50 * Fraction(3, 4) + 20 * Fraction(1, 2) + 20 * Fraction(2, 3) + 10


def test_equal_scores_from_different_components_are_identical():
    """LLD §7.6: the worked example and a 2-of-3 job (no nice list, no minimum, other city) both
    score exactly 71 2/3. Plain floats would store them as two different values."""
    other_job = job(["Python", "FastAPI", "Kafka"], [], None, "Mumbai")
    first = score_pair(WORKED_JOB, WORKED_CANDIDATE)
    second = score_pair(other_job, WORKED_CANDIDATE)
    assert first.score == second.score == Fraction(215, 3)
    assert float(first.score) == float(second.score)
    plain_first = 70 * (3 / 4) + 15 * (1 / 2) + 10 * (2 / 3) + 5 * 1
    plain_second = 70 * (2 / 3) + 15 * 1 + 10 * 1 + 5 * 0
    assert plain_first != plain_second  # 71.66666666666667 vs 71.66666666666666
