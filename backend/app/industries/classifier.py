"""The industry of a job posting, from its title, skills and description (explainable rules).

The rules are data (`industries.json`): for each industry, terms for the title and terms for the
description; and for skills, the industry of each skill category of the taxonomy, with a few
per-skill exceptions ("Excel" or "Agile" point to no industry, "Figma" points to design).

Points (each term counted once):
- a title term: 3 points (at most 6 per industry): the title is the strongest evidence;
- a skill whose category belongs to the industry: 1 point (at most 4);
- a description term: 1 point (at most 3): descriptions also mention benefits and the company.

The industry with the most points wins if it has at least 3 and strictly more than the next one.
Otherwise the job is `other` ("Other / Unclassified"): a weak or tied signal is never forced into
an industry. Matching works like skill matching: lower case, whole words, longest term first, no
overlaps, so "data engineer" is one term and "software engineer" counts only "software".

Industries never change a match score; they only help people browse and filter jobs.
"""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from app.industries import INDUSTRIES
from app.skills.normalizer import get_taxonomy, normalize_text

RULES_FILE = Path(__file__).with_name("industries.json")
OTHER = "other"
MIN_POINTS = 3
POINTS = {"title": 3, "skill": 1, "description": 1}
MAX_POINTS = {"title": 6, "skill": 4, "description": 3}  # per industry and per kind of evidence

Evidence = Literal["title", "skill", "description"]


@dataclass(frozen=True)
class Signal:
    """One piece of evidence: a term of the title or description, or a skill."""

    kind: Evidence
    term: str
    industry: str


class _Terms:
    """Whole-word terms of one kind (title or description), each pointing to one industry."""

    def __init__(self, terms: dict[str, str]):
        self.industry_of = terms
        alternation = "|".join(re.escape(t).replace(r"\ ", r"[\s\-]+") for t in sorted(terms, key=len, reverse=True))
        self._pattern = re.compile(rf"(?<![a-z0-9])(?:{alternation})(?![a-z0-9])") if terms else None

    def find(self, text: str | None) -> list[tuple[str, str]]:
        """(term, industry) for each occurrence, left to right, without overlaps."""
        if not text or self._pattern is None:
            return []
        found = []
        for match in self._pattern.finditer(normalize_text(text)):
            term = re.sub(r"[\s\-]+", " ", match.group(0))
            found.append((term, self.industry_of[term]))
        return found


class Rules:
    """The industries, their labels and their evidence, loaded from `industries.json` and checked."""

    def __init__(self, data: dict):
        industries = data["industries"]
        if tuple(industries) != INDUSTRIES:
            raise ValueError(f"industries.json must list exactly {INDUSTRIES}, in that order")
        self.labels: dict[str, str] = {code: entry["label"] for code, entry in industries.items()}
        self.codes: tuple[str, ...] = tuple(industries)
        self.terms: dict[str, _Terms] = {}
        for kind in ("title", "description"):
            terms: dict[str, str] = {}
            for code, entry in industries.items():
                for term in entry.get(kind, []):
                    key = re.sub(r"\s+", " ", normalize_text(term).strip())
                    if terms.get(key, code) != code:
                        raise ValueError(f"{kind} term {term!r} belongs to both {terms[key]} and {code}")
                    terms[key] = code
            if any(code == OTHER for code in terms.values()):
                raise ValueError(f"the {OTHER!r} industry has no terms: it is what remains")
            self.terms[kind] = _Terms(terms)

        taxonomy = get_taxonomy()
        self.skill_industry: dict[str, str | None] = {}
        for name in taxonomy.canonical_names:
            self.skill_industry[name] = data["skill_categories"].get(taxonomy.categories[name] or "")
        for name, code in data["skills"].items():
            if name not in self.skill_industry:
                raise ValueError(f"{name!r} is not a skill of the taxonomy")
            self.skill_industry[name] = code
        for code in [*data["skill_categories"].values(), *data["skills"].values()]:
            if code == OTHER or (code is not None and code not in self.labels):
                raise ValueError(f"a skill cannot point to industry {code!r}")


@lru_cache
def get_rules() -> Rules:
    return Rules(json.loads(RULES_FILE.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class Classification:
    industry: str
    points: dict[str, int]          # every industry except `other`, including those with 0 points
    signals: tuple[Signal, ...]     # the evidence that was counted, in title, skill, description order

    def reasons(self, industry: str | None = None) -> list[str]:
        """Sentences that explain `industry` (default: the result), e.g. 'Title: "nurse" (+3)'."""
        rules = get_rules()
        industry = industry or self.industry
        if industry == OTHER:
            return [self._why_other()]
        lines = []
        for kind, name in (("title", "Title"), ("skill", "Skills"), ("description", "Description")):
            terms = [s.term for s in self.signals if s.industry == industry and s.kind == kind]
            if terms:
                shown = ", ".join(terms if kind == "skill" else (f'"{t}"' for t in terms))
                lines.append(f"{name}: {shown} (+{POINTS[kind] * len(terms)})")
        if not lines:
            lines.append(f"No current evidence for {rules.labels[industry]}.")
        return lines

    def _why_other(self) -> str:
        labels = get_rules().labels
        ranked = sorted(self.points.items(), key=lambda item: (-item[1], item[0]))
        (first, top), (second, runner_up) = ranked[0], ranked[1]
        if top == 0:
            return "No industry terms in the title, skills or description."
        if top < MIN_POINTS:
            return (f"Too little evidence: the strongest industry, {labels[first]}, has {top} of the "
                    f"{MIN_POINTS} points needed.")
        return f"{labels[first]} and {labels[second]} are equally likely ({top} points each)."


def classify(title: str | None, description: str | None, skills: Iterable[str]) -> Classification:
    """The industry of a job from its title, description and canonical skill names."""
    rules = get_rules()
    points = {code: 0 for code in rules.codes if code != OTHER}
    signals: list[Signal] = []

    def count(kind: Evidence, found: Iterable[tuple[str, str]]) -> None:
        per_industry: dict[str, list[str]] = {}
        for term, industry in found:
            terms = per_industry.setdefault(industry, [])
            if term not in terms:
                terms.append(term)
        for industry, terms in per_industry.items():
            counted = terms[: MAX_POINTS[kind] // POINTS[kind]]
            points[industry] += POINTS[kind] * len(counted)
            signals.extend(Signal(kind, term, industry) for term in counted)

    count("title", rules.terms["title"].find(title))
    count("skill", ((name, rules.skill_industry[name]) for name in sorted(set(skills))
                    if rules.skill_industry.get(name)))
    count("description", rules.terms["description"].find(description))

    ranked = sorted(points.items(), key=lambda item: (-item[1], item[0]))
    (best, top), (_, runner_up) = ranked[0], ranked[1]
    industry = best if top >= MIN_POINTS and top > runner_up else OTHER
    order = {"title": 0, "skill": 1, "description": 2}
    return Classification(industry, points, tuple(sorted(signals, key=lambda s: order[s.kind])))


def industry_codes() -> tuple[str, ...]:
    return get_rules().codes


def industry_label(code: str) -> str:
    return get_rules().labels.get(code, code)
