"""The scoring formula and its edge-case rules, computed exactly (LLD §7.4-7.6, ADR-016, ADR-017).

    score = 70·R + 15·N + 10·E + 5·L        (weights from MATCH_WEIGHTS, adding up to 100)

R, N, E and L are `fractions.Fraction` values between 0 and 1, so the score is exact:
mathematically equal scores are identical (and reach the tie-breaker), and different scores never
collapse into one. The score is converted to a float once, when it is stored (DOUBLE PRECISION),
and rounded only for display (`explanation.display`).

Edge cases (LLD §7.5):

    job has required skills but no nice-to-have list    N = 1
    job has no skills at all (no required, no nice)     R = 0 and N = 0  (open question O2, decided)
    job has nice-to-have skills but no required ones    R = 0, flagged; N as usual
    job has no minimum experience (None or 0)           E = 1
    minimum set, candidate's years unknown              E = 0
    job remote                                          L = 1
    same city (after normalization)                     L = 1
    candidate or job city unknown, job not remote       L = 0

Skills are canonical names (normalized when jobs and resumes were saved), compared as sets, so a
skill listed twice counts once and candidate skills the job does not mention change nothing.
"""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from app.locations.normalizer import normalize_city

# Why a component got its value; stored in the breakdown, so the explanation can say it.
RATIO = "ratio"                                # matched ÷ total (skills), years ÷ minimum (experience)
NONE_LISTED = "none_listed"                    # N = 1: the job has required skills but no nice-to-have list
NO_REQUIRED_IDENTIFIED = "no_required_identified"  # R = 0: no required skills, but nice-to-have ones exist
NO_SKILLS_IDENTIFIED = "no_skills_identified"  # R = 0 and N = 0: no skills could be found for the job at all
NO_MINIMUM = "no_minimum"                      # E = 1
YEARS_UNKNOWN = "years_unknown"                # E = 0
REMOTE = "remote"                              # L = 1
SAME_CITY = "same_city"                        # L = 1
DIFFERENT_CITY = "different_city"              # L = 0
CANDIDATE_CITY_UNKNOWN = "candidate_city_unknown"  # L = 0
JOB_CITY_UNKNOWN = "job_city_unknown"          # L = 0

ZERO = Fraction(0)
ONE = Fraction(1)


@dataclass(frozen=True)
class Weights:
    required: Fraction
    nice: Fraction
    experience: Fraction
    location: Fraction

    @classmethod
    def from_settings(cls, weights) -> "Weights":
        """From `Settings.match_weights` (floats). `str()` first, so 70.0 becomes exactly 70
        and a decimal weight such as 33.3 becomes exactly 333/10, not its binary approximation."""
        return cls(*(Fraction(str(value)) for value in
                     (weights.required, weights.nice, weights.experience, weights.location)))

    @property
    def total(self) -> Fraction:
        return self.required + self.nice + self.experience + self.location


BASELINE_WEIGHTS = Weights(Fraction(70), Fraction(15), Fraction(10), Fraction(5))


@dataclass(frozen=True)
class JobProfile:
    """What the score needs from a job."""

    required: frozenset[str]
    nice_to_have: frozenset[str]
    min_experience_years: Decimal | None
    location: str | None
    is_remote: bool

    @property
    def has_no_skills(self) -> bool:
        return not self.required and not self.nice_to_have


@dataclass(frozen=True)
class CandidateProfile:
    """What the score needs from a candidate."""

    skills: frozenset[str]
    years_experience: Decimal | None
    city: str | None


@dataclass(frozen=True)
class SkillPart:
    matched: tuple[str, ...]   # sorted canonical names
    missing: tuple[str, ...]
    fit: Fraction              # R or N
    points: Fraction
    rule: str

    @property
    def total(self) -> int:
        return len(self.matched) + len(self.missing)


@dataclass(frozen=True)
class ExperiencePart:
    candidate_years: Decimal | None
    minimum: Decimal | None
    fit: Fraction
    points: Fraction
    rule: str


@dataclass(frozen=True)
class LocationPart:
    candidate_city: str | None
    job_location: str | None
    job_city: str | None       # the city found in job_location, as compared
    fit: Fraction
    points: Fraction
    rule: str


@dataclass(frozen=True)
class ScoreResult:
    score: Fraction            # exact, clamped to [0, 100]
    required: SkillPart
    nice_to_have: SkillPart
    experience: ExperiencePart
    location: LocationPart


def _sorted(names) -> tuple[str, ...]:
    return tuple(sorted(names, key=lambda name: (name.casefold(), name)))


def _skill_part(wanted: frozenset[str], has: frozenset[str], fit: Fraction, weight: Fraction, rule: str) -> SkillPart:
    return SkillPart(matched=_sorted(wanted & has), missing=_sorted(wanted - has), fit=fit, points=weight * fit, rule=rule)


def score_skills(job: JobProfile, skills: frozenset[str], weights: Weights) -> tuple[SkillPart, SkillPart]:
    """R and N with their edge cases (LLD §7.5)."""
    required, nice = job.required, job.nice_to_have
    if job.has_no_skills:
        # O2: an empty skill list almost always means extraction failed. Neither 70 nor 15 free
        # points: such a job scores at most E + L (15 with the baseline weights).
        return (_skill_part(required, skills, ZERO, weights.required, NO_SKILLS_IDENTIFIED),
                _skill_part(nice, skills, ZERO, weights.nice, NO_SKILLS_IDENTIFIED))
    if required:
        r_part = _skill_part(required, skills, Fraction(len(required & skills), len(required)), weights.required, RATIO)
    else:
        r_part = _skill_part(required, skills, ZERO, weights.required, NO_REQUIRED_IDENTIFIED)
    if nice:
        n_part = _skill_part(nice, skills, Fraction(len(nice & skills), len(nice)), weights.nice, RATIO)
    else:
        # The candidate misses none of the job's nice-to-haves; otherwise a perfect candidate
        # could score at most 85.
        n_part = _skill_part(nice, skills, ONE, weights.nice, NONE_LISTED)
    return r_part, n_part


def score_experience(minimum: Decimal | None, years: Decimal | None, weight: Fraction) -> ExperiencePart:
    """E = min(1, years / minimum): linear below the minimum (HLD §10.3)."""
    if minimum is None or minimum == 0:
        fit, rule = ONE, NO_MINIMUM
    elif years is None:
        fit, rule = ZERO, YEARS_UNKNOWN
    else:
        fit, rule = min(ONE, Fraction(years) / Fraction(minimum)), RATIO
    return ExperiencePart(candidate_years=years, minimum=minimum, fit=fit, points=weight * fit, rule=rule)


def city_of(text: str | None) -> str | None:
    """The city in a candidate's city or a job's location, as it is compared.

    A known city (app/locations/cities.json) gives its canonical name, so "Bangalore, India"
    and "Bengaluru" are the same city. Otherwise the city part of the text is used: everything
    before the first comma, with spaces tidied ("Stewartbury, AA" gives "Stewartbury").
    """
    canonical = normalize_city(text)
    if canonical:
        return canonical
    part = " ".join((text or "").split(",")[0].split())
    return part or None


def same_city(a: str, b: str) -> bool:
    """Case-insensitive comparison of two names returned by `city_of`."""
    return a.casefold() == b.casefold()


def score_location(job: JobProfile, candidate_city: str | None, weight: Fraction) -> LocationPart:
    """L = 1 for a remote job or the same normalized city, otherwise 0 (HLD §10.4).

    "Hybrid" jobs count as city-based: `is_remote` is set only for remote jobs when they are saved.
    """
    job_city = city_of(job.location)
    candidate = city_of(candidate_city)
    if job.is_remote:
        fit, rule = ONE, REMOTE
    elif candidate is None:
        fit, rule = ZERO, CANDIDATE_CITY_UNKNOWN
    elif job_city is None:
        fit, rule = ZERO, JOB_CITY_UNKNOWN
    elif same_city(candidate, job_city):
        fit, rule = ONE, SAME_CITY
    else:
        fit, rule = ZERO, DIFFERENT_CITY
    return LocationPart(candidate_city=candidate_city, job_location=job.location, job_city=job_city,
                        fit=fit, points=weight * fit, rule=rule)


def clamp(score: Fraction) -> Fraction:
    """A guard: with factors in [0, 1] and weights adding up to 100 the score is already in range."""
    return min(Fraction(100), max(ZERO, score))


def score_pair(job: JobProfile, candidate: CandidateProfile, weights: Weights = BASELINE_WEIGHTS) -> ScoreResult:
    """The exact score of one (candidate, job) pair with its four components."""
    required, nice = score_skills(job, candidate.skills, weights)
    experience = score_experience(job.min_experience_years, candidate.years_experience, weights.experience)
    location = score_location(job, candidate.city, weights.location)
    total = required.points + nice.points + experience.points + location.points
    return ScoreResult(score=clamp(total), required=required, nice_to_have=nice, experience=experience,
                       location=location)
