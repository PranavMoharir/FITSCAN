"""Matched and missing skills, the stored breakdown, the explanation sentence, display rounding (LLD §7.7).

The explanation is generated from the breakdown with one fixed template (HLD §10.8), so it
always agrees with the score:

    "Score 71.67/100. Has 3 of 4 required skills (52.50 pts; missing Docker). Has 1 of 2
     nice-to-have skills (7.50 pts; missing Kubernetes). 2 years of experience against a 3-year
     minimum (6.67 pts). Same city, Pune (5.00 pts)."

Rounding happens only here, for display. The stored score and breakdown keep full precision, and
ranking never uses a rounded value (LLD §7.6). The API uses the same `display` function, so the
score in the sentence and the score in the response are always the same number.

Pure Python: the API imports this module too.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.matching import scoring
from app.matching.scoring import ScoreResult

SCORE_PLACES = 2   # scores and points
FIT_PLACES = 3     # ratios and fits, e.g. 0.667


def display(value: float | None, places: int = SCORE_PLACES) -> float | None:
    """Round a stored value for display: half away from zero, on the value's shortest decimal form."""
    if value is None:
        return None
    return float(Decimal(repr(float(value))).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def _pts(value: float) -> str:
    return f"{display(value):.2f}"


def _number(value: Decimal | None) -> int | float | None:
    """A Decimal from a numeric column as a JSON number: 2 rather than 2.0, 2.5 stays 2.5."""
    if value is None:
        return None
    return int(value) if value == value.to_integral_value() else float(value)


def _years(value: float | int) -> str:
    """2 -> "2", 2.5 -> "2.5"."""
    return f"{value:g}"


def skill_lists(result: ScoreResult) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """matched_skills and missing_skills: required first, then nice-to-have, each alphabetical."""
    matched = ([{"skill": s, "level": "required"} for s in result.required.matched]
               + [{"skill": s, "level": "nice_to_have"} for s in result.nice_to_have.matched])
    missing = ([{"skill": s, "level": "required"} for s in result.required.missing]
               + [{"skill": s, "level": "nice_to_have"} for s in result.nice_to_have.missing])
    return matched, missing


def breakdown(result: ScoreResult) -> dict[str, Any]:
    """`score_breakdown`: counts, ratios, points and the rule applied, for every component (LLD §3.3).

    Values are full-precision floats; nothing is rounded here.
    """
    def skills(part: scoring.SkillPart) -> dict[str, Any]:
        return {"matched": len(part.matched), "total": part.total, "ratio": float(part.fit),
                "points": float(part.points), "rule": part.rule}

    experience, location = result.experience, result.location
    return {
        "required": skills(result.required),
        "nice_to_have": skills(result.nice_to_have),
        "experience": {"candidate_years": _number(experience.candidate_years), "minimum": _number(experience.minimum),
                       "fit": float(experience.fit), "points": float(experience.points), "rule": experience.rule},
        "location": {"candidate_city": location.candidate_city, "job_location": location.job_location,
                     "job_city": location.job_city, "fit": float(location.fit), "points": float(location.points),
                     "rule": location.rule},
    }


def _missing_names(missing_skills: list[dict[str, str]], level: str) -> list[str]:
    return [item["skill"] for item in missing_skills if item["level"] == level]


def _skills_sentence(kind: str, part: dict[str, Any], missing: list[str]) -> str:
    noun = "skill" if part["total"] == 1 else "skills"
    text = f"Has {part['matched']} of {part['total']} {kind} {noun} ({_pts(part['points'])} pts"
    if missing:
        text += "; missing " + ", ".join(missing)
    return text + ")."


def _experience_sentence(part: dict[str, Any]) -> str:
    points = _pts(part["points"])
    if part["rule"] == scoring.NO_MINIMUM:
        return f"No minimum experience required ({points} pts)."
    minimum = _years(part["minimum"])
    if part["rule"] == scoring.YEARS_UNKNOWN:
        unit = "year" if part["minimum"] == 1 else "years"
        return f"Experience not found in resume; the job asks for at least {minimum} {unit} ({points} pts)."
    unit = "year" if part["candidate_years"] == 1 else "years"
    return f"{_years(part['candidate_years'])} {unit} of experience against a {minimum}-year minimum ({points} pts)."


def _location_sentence(part: dict[str, Any]) -> str:
    points = _pts(part["points"])
    rule = part["rule"]
    if rule == scoring.REMOTE:
        return f"Remote job ({points} pts)."
    if rule == scoring.SAME_CITY:
        return f"Same city, {part['job_city']} ({points} pts)."
    if rule == scoring.DIFFERENT_CITY:
        return f"Different city: candidate in {part['candidate_city']}, job in {part['job_location']} ({points} pts)."
    if rule == scoring.CANDIDATE_CITY_UNKNOWN:
        return f"Candidate's city not found in resume ({points} pts)."
    return f"Job location not given ({points} pts)."


def explain(score: float, parts: dict[str, Any], missing_skills: list[dict[str, str]]) -> str:
    """The explanation sentence, from the stored score, breakdown and missing skills only."""
    required, nice = parts["required"], parts["nice_to_have"]
    sentences = [f"Score {_pts(score)}/100."]
    if required["rule"] == scoring.NO_SKILLS_IDENTIFIED:
        sentences.append("No required or nice-to-have skills could be identified for this job, "
                         f"so it gets no skill points ({_pts(required['points'] + nice['points'])} pts).")
    else:
        if required["rule"] == scoring.NO_REQUIRED_IDENTIFIED:
            sentences.append(f"No required skills could be identified for this job ({_pts(required['points'])} pts).")
        else:
            sentences.append(_skills_sentence("required", required, _missing_names(missing_skills, "required")))
        if nice["rule"] == scoring.NONE_LISTED:
            sentences.append(f"The job lists no nice-to-have skills ({_pts(nice['points'])} pts).")
        else:
            sentences.append(_skills_sentence("nice-to-have", nice, _missing_names(missing_skills, "nice_to_have")))
    sentences.append(_experience_sentence(parts["experience"]))
    sentences.append(_location_sentence(parts["location"]))
    return " ".join(sentences)


def display_breakdown(parts: dict[str, Any]) -> dict[str, Any]:
    """The stored breakdown as the API shows it: points to 2 decimals, ratios and fits to 3."""
    shown: dict[str, Any] = {}
    for name, component in parts.items():
        item = dict(component)
        if "points" in item:
            item["points"] = display(item["points"])
        for key in ("ratio", "fit"):
            if key in item:
                item[key] = display(item[key], FIT_PLACES)
        shown[name] = item
    return shown
