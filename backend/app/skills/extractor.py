"""Find skills in text, and split a job's skills into required and nice-to-have (LLD §6.8).

Steps for any text:
1. `Taxonomy.find` returns every alias occurrence (longest match first, word boundaries).
2. Known false phrases ("R&D", "go-to-market", "C-level", "the rest of") remove what they cover.
3. Ambiguous short words ("go", "r", "c", "rest", "spring", "swift", ...) count only in a clear
   skill context: a list item of their own ("Skills: Python, Go, Docker"), or a case-sensitive
   form such as "Go", "R" or "REST". Outside a Requirements or Nice-to-have section, a capitalized
   word at the start of a sentence ("Go to ...", "Spring is ...") does not count.
4. The canonical names are de-duplicated.

For jobs, the description is then split by headings ("Requirements", "Nice to have", ...) and by
inline qualifiers ("Docker is a plus"). Skills not marked nice-to-have are required, and a skill
found in both groups is required.
"""

import re
from dataclasses import dataclass, field

from app.skills.normalizer import SkillMatch, Taxonomy, get_taxonomy, normalize_text

# Ambiguous alias -> the case-sensitive forms that make it a skill outside a list.
AMBIGUOUS_ALIASES: dict[str, tuple[str, ...]] = {
    "go": ("Go",),
    "r": ("R",),
    "c": ("C",),
    "rest": ("REST",),
    "spring": ("Spring",),
    "swift": ("Swift",),
    "excel": ("Excel",),
    "spark": ("Spark",),
    "ml": ("ML",),
}
NEGATIVE_PHRASES = re.compile(r"r\s?&\s?d|go-to-market|c-level|c-suite|the rest of|on the go")

REQUIRED_HEADINGS = ("requirements", "required skills", "required", "must have", "must-have",
                     "qualifications", "what you need", "what you'll need")
NICE_HEADINGS = ("nice to have", "nice-to-have", "bonus points", "bonus", "preferred", "plus")
INLINE_NICE = re.compile(r"\b(preferred|a plus|nice to have|nice-to-have|bonus|ideally)\b")
_LIST_SEPARATORS = r"[,;|/•\n]"
_BULLET = re.compile(r"^\s*(?:[-*•#>]+|\d+[.)])\s*")


@dataclass
class JobSkills:
    required: list[str] = field(default_factory=list)
    nice_to_have: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)  # skill-like list items that matched no alias


def _is_list_item(normalized: str, match: SkillMatch) -> bool:
    """True if the match is a list item of its own, for example "go" in "python, go, docker"."""
    left = max(normalized.rfind(sep, 0, match.start) for sep in ",;|/•\n:")
    right_candidates = [i for i in (normalized.find(sep, match.end) for sep in ",;|/•\n") if i != -1]
    right = min(right_candidates) if right_candidates else len(normalized)
    item = normalized[left + 1:right].strip(" .\t-*")
    item = re.sub(r"^(and|or)\s+", "", item)
    in_list = left != -1 or right != len(normalized)
    return in_list and item == normalized[match.start:match.end]


def _at_sentence_start(text: str, start: int) -> bool:
    before = text[:start].rstrip(" \t*-•")
    return not before or before[-1] in ".!?:\n"


def find_skills(text: str, taxonomy: Taxonomy | None = None, *, skill_section: bool = False) -> list[SkillMatch]:
    """All accepted skill occurrences in the text, after the ambiguity and negative-phrase rules.

    `skill_section` is True for text under a Requirements or Nice-to-have heading.
    """
    taxonomy = taxonomy or get_taxonomy()
    normalized = normalize_text(text)
    blocked = [(m.start(), m.end()) for m in NEGATIVE_PHRASES.finditer(normalized)]
    accepted = []
    for match in taxonomy.find(text):
        if any(start < match.end and match.start < end for start, end in blocked):
            continue
        alias = normalized[match.start:match.end]
        forms = AMBIGUOUS_ALIASES.get(alias)
        if forms is not None:
            original = text[match.start:match.end]
            title_case_word = original in forms and original[:1].isupper() and original[1:].islower() and len(original) > 1
            sentence_start = title_case_word and _at_sentence_start(text, match.start)
            case_ok = original in forms and (skill_section or not sentence_start)
            if not (case_ok or _is_list_item(normalized, match)):
                continue
        accepted.append(match)
    return accepted


def extract_skills(text: str | None) -> list[str]:
    """Sorted canonical skill names found in the text."""
    if not text:
        return []
    return sorted({m.canonical for m in find_skills(text)})


def _heading_level(line: str) -> tuple[str | None, str, bool]:
    """(level, rest of the line, is_heading). level is "required", "nice" or None for other headings."""
    stripped = _BULLET.sub("", line).strip().strip("*_ ")
    lowered = stripped.lower()
    for level, keywords in (("nice", NICE_HEADINGS), ("required", REQUIRED_HEADINGS)):
        for keyword in keywords:
            if lowered.startswith(keyword):
                rest = stripped[len(keyword):]
                if rest.lstrip().startswith(":"):
                    return level, rest.lstrip()[1:].strip(), True
                if len(lowered.split()) <= 5 and not rest.strip(" :"):
                    return level, "", True
    if stripped.endswith(":") and len(stripped.split()) <= 5:
        return None, "", True  # another heading, e.g. "About us:" or "Responsibilities:"
    return None, stripped, False


def _unmatched_items(line: str) -> list[str]:
    """Short list items that contain no taxonomy alias at all: possible gaps in the taxonomy.

    This asks only "is it in the taxonomy?". The context rules of `find_skills` are not applied
    here: a lone lowercase "go" fails them, yet "go" is an alias and must not be reported.
    """
    taxonomy = get_taxonomy()
    items = []
    for item in re.split(_LIST_SEPARATORS, normalize_text(line)):
        item = re.sub(r"^(and|or)\s+", "", item.strip(" .\t-*()"))
        if item and len(item) <= 30 and 1 <= len(item.split()) <= 3 and not taxonomy.find(item):
            items.append(item)
    return items


def extract_job_skills(
    description: str | None,
    structured_required: list[str] | None = None,
    structured_nice: list[str] | None = None,
) -> JobSkills:
    """Required and nice-to-have canonical skills for a job posting."""
    taxonomy = get_taxonomy()
    required: set[str] = set()
    nice: set[str] = set()
    unmatched: list[str] = []

    if structured_required or structured_nice:  # structured site fields come first
        for terms, target in ((structured_required or [], required), (structured_nice or [], nice)):
            for term in terms:
                found = {taxonomy.canonical(term)} - {None} or set(extract_skills(term))
                if found:
                    target.update(found)
                else:
                    unmatched.append(normalize_text(term).strip())
    else:
        level: str | None = None
        for raw_line in (description or "").splitlines():
            line_level, content, is_heading = _heading_level(raw_line)
            if is_heading:
                level = line_level
            if not content:
                continue
            in_skill_section = level is not None
            for sentence in re.split(r"(?<=[.;!?])\s+", content):
                names = {m.canonical for m in find_skills(sentence, skill_section=in_skill_section)}
                if INLINE_NICE.search(normalize_text(sentence)) or level == "nice":
                    nice.update(names)
                else:
                    required.update(names)
            if in_skill_section or content.count(",") >= 2:
                unmatched.extend(_unmatched_items(content))

    nice -= required  # required wins
    return JobSkills(sorted(required), sorted(nice), unmatched)
