"""Candidate fields from a resume's text, with simple rules that can be explained (LLD §6.6, HLD §8.7).

| Field            | Rule                                                                          |
|------------------|-------------------------------------------------------------------------------|
| sections         | Short lines such as "Summary", "Work Experience", "Education", "Skills"        |
| name             | The largest-font line near the top of page 1. OCR text has no font sizes:    |
|                  | the first header line that is not contact information. Otherwise a          |
|                  | placeholder from the file name, with a warning.                              |
| email            | Regular expression; `CandidateRecord` validates it (invalid -> null + warning) |
| phone            | Regular expression, normalized to digits with an optional leading "+"         |
| city             | Contact or header lines matched against the shared city list (app/locations) |
| current_title    | The line directly under the name, otherwise the first role in Experience     |
| years_experience | An explicit "6+ years of experience" first; otherwise the date ranges in     |
|                  | Experience are merged, so overlapping jobs are not counted twice             |
| education        | Entries of the Education section: degree, institution, years                 |
| summary          | The Summary/Profile section, otherwise the first paragraph                    |
| skills           | The shared skill extractor over the Skills section, table cells and all text |

"Present" in a date range means `today`, which the caller passes in (the parse date in normal
use, a fixed date in tests), so results never change from day to day (LLD decision LLD-11).
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import PurePath

from app.locations.normalizer import CityList, load_cities
from app.resumes.text_extraction import ExtractedText, Line
from app.skills.extractor import extract_resume_skills

NAME_TOP_SHARE = 0.3        # the name is in the top 30 % of page 1
MAX_SUMMARY_CHARS = 1000
MIN_PARAGRAPH_WORDS = 12
MAX_EDUCATION_ENTRIES = 10

# --- Sections ---------------------------------------------------------------------------------------

SECTION_HEADINGS: dict[str, tuple[str, ...]] = {
    "summary": ("summary", "professional summary", "profile", "professional profile", "profile summary",
                "career summary", "about me", "about", "objective", "career objective"),
    "experience": ("experience", "work experience", "professional experience", "employment",
                   "employment history", "work history", "career history", "relevant experience"),
    "education": ("education", "academic background", "academic qualifications", "educational qualifications",
                  "education and training", "academics"),
    "skills": ("skills", "technical skills", "key skills", "core skills", "skill set", "skillset",
               "skills and tools", "tools and technologies", "technologies", "tech stack",
               "core competencies", "competencies", "technical expertise", "areas of expertise"),
    "contact": ("contact", "contact details", "contact information", "contact info", "personal details",
                "personal information"),
    "other": ("projects", "personal projects", "key projects", "certifications", "certificates", "courses",
              "training", "languages", "interests", "hobbies", "achievements", "awards", "honors",
              "publications", "references", "volunteering", "volunteer experience", "declaration",
              "activities", "extracurricular activities", "strengths"),
}
_HEADING_TO_SECTION = {heading: section for section, headings in SECTION_HEADINGS.items() for heading in headings}
_INLINE_HEADING = re.compile(r"^\s*([A-Za-z][A-Za-z &/]{1,40}?)\s*:\s*(\S.*)$")


def _heading_key(text: str) -> str:
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z ]+", " ", text)
    return " ".join(text.split())


def heading_of(text: str) -> tuple[str | None, str]:
    """(section, text after the heading) if the line is a section heading, else (None, "")."""
    if len(text.split()) <= 5:
        section = _HEADING_TO_SECTION.get(_heading_key(text))
        if section:
            return section, ""
    inline = _INLINE_HEADING.match(text)  # "Skills: Python, Go, Docker"
    if inline:
        section = _HEADING_TO_SECTION.get(_heading_key(inline.group(1)))
        if section:
            return section, inline.group(2).strip()
    return None, ""


def split_sections(lines: list[Line]) -> dict[str, list[Line]]:
    """Lines grouped by section. Lines before the first heading are the "header"."""
    sections: dict[str, list[Line]] = {"header": []}
    current = "header"
    for line in lines:
        section, rest = heading_of(line.text)
        if section:
            current = section
            sections.setdefault(current, [])
            if rest:
                sections[current].append(Line(rest, line.page, line.block, line.size, line.bold, line.top))
            continue
        sections.setdefault(current, []).append(line)
    return sections


# --- Contact information ----------------------------------------------------------------------------

_EMAIL_LIKE = re.compile(r"[\w.+%'-]+@[\w-]+(?:\.[\w-]+)*")
_URL = re.compile(r"(?:https?://|www\.)\S+|\b(?:linkedin|github)\.com/\S*", re.I)
_PHONE_LABELLED = re.compile(
    r"\b(?:phone|mobile|mob|tel|telephone|cell|contact\s+no)\b\.?\s*(?:no\.?|number|#)?\s*[:.\-]?\s*(\+?[\d(][\d\s().\-]{2,}\d)",
    re.I)
_PHONE = re.compile(r"(?<![\w+])(\+?\(?\d[\d\s().\-]{7,}\d)(?!\w)")


def normalize_phone(raw: str) -> str:
    """Digits only, with a leading "+" if the number had one: "(+91) 98765-43210" -> "+919876543210"."""
    raw = raw.strip()
    plus = raw.startswith("+") or raw.startswith("(+")
    return ("+" if plus else "") + re.sub(r"\D", "", raw)


def find_email(lines: list[Line]) -> str | None:
    """The first email-like text. It is validated later, so a malformed one gets a warning."""
    for line in lines:
        match = _EMAIL_LIKE.search(line.text)
        if match:
            return match.group(0).strip(".'-")
    return None


def find_phone(contact_lines: list[Line], all_lines: list[Line]) -> str | None:
    """A labelled number anywhere ("Phone: ..."), otherwise a 10-15 digit number in the contact lines."""
    for line in all_lines:
        match = _PHONE_LABELLED.search(line.text)
        if match:
            return normalize_phone(match.group(1))  # even if malformed: validation adds the warning
    for line in contact_lines:
        for match in _PHONE.finditer(_URL.sub(" ", line.text)):
            number = normalize_phone(match.group(1))
            if 10 <= len(number.lstrip("+")) <= 15:
                return number
    return None


def is_contact(text: str) -> bool:
    return bool(_EMAIL_LIKE.search(text) or _URL.search(text) or _PHONE_LABELLED.search(text)
                or any(10 <= len(normalize_phone(m.group(1)).lstrip("+")) <= 15 for m in _PHONE.finditer(text)))


_LOCATION_LABEL = re.compile(r"^\s*(?:location|address|city|based in|current location)\b", re.I)


def find_city(contact_lines: list[Line], all_lines: list[Line], cities: CityList) -> str | None:
    for line in contact_lines + [line for line in all_lines if _LOCATION_LABEL.match(line.text)]:
        city = cities.find(line.text)
        if city:
            return city
    return None


# --- Name and current title -----------------------------------------------------------------------

NOT_NAME_WORDS = {"resume", "résumé", "curriculum", "vitae", "cv", "profile", "contact", "page"}
TITLE_WORDS = {"engineer", "developer", "manager", "analyst", "scientist", "designer", "consultant", "lead",
               "architect", "intern", "administrator", "specialist", "officer", "director", "head", "associate",
               "executive", "tester", "programmer", "devops", "sre", "qa", "student", "graduate", "trainee"}


def looks_like_name(text: str) -> bool:
    words = text.split()
    if not 1 <= len(words) <= 5 or len(text) > 60:
        return False
    if any(w.lower().strip(".,") in NOT_NAME_WORDS | TITLE_WORDS for w in words):
        return False
    return all(w.replace(".", "").replace("'", "").replace("-", "").isalpha() for w in words)


def _tidy_name(text: str) -> str:
    return text.title() if text.isupper() else text


def find_name(extracted: ExtractedText, header: list[Line]) -> Line | None:
    """The largest-font name-like line near the top of page 1 (OCR text: the first one in the header)."""
    if not extracted.pages:
        return None
    first = extracted.pages[0]
    if first.source == "ocr":
        return next((l for l in header if l.page == 1 and looks_like_name(l.text) and not is_contact(l.text)), None)
    candidates = [l for l in first.lines if l.top <= NAME_TOP_SHARE * first.height and looks_like_name(l.text)
                  and not is_contact(l.text) and heading_of(l.text)[0] is None]
    if not candidates:
        return None
    return max(candidates, key=lambda l: (round(l.size, 1), -l.top))


def placeholder_name(source_file: str) -> str:
    """Used when no name is found (LLD §3.3): the file name without its extension."""
    stem = " ".join(re.split(r"[_\-.\s]+", PurePath(source_file).stem)).strip()
    return stem[:200] or "Unnamed candidate"


_DATE_RANGE_TEXT = re.compile(
    r"\(?\b(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*,?\s*)?(?:\d{1,2}\s*[/.-]\s*)?"
    r"(?:19|20)\d{2}\s*(?:-|–|—|to|until|till)\s*(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*,?\s*)?"
    r"(?:\d{1,2}\s*[/.-]\s*)?(?:(?:19|20)\d{2}|present|current|now|today|till date|to date)\b\)?", re.I)
_TITLE_SEPARATORS = re.compile(r"\s+(?:at|@)\s+|\s*[|,–—]\s*|\s+-\s+")


def looks_like_title(text: str, cities: CityList) -> bool:
    words = text.split()
    if not 1 <= len(words) <= 10 or len(text) > 100 or is_contact(text) or heading_of(text)[0]:
        return False
    if text.endswith(".") or sum(ch.isdigit() for ch in text) > 4:
        return False
    return not (cities.find(text) and len(words) <= 3)  # "Pune, India" is a location, not a title


def role_from_experience_line(text: str) -> str | None:
    """"Senior Engineer, Acme Corp (Jan 2019 - Present)" -> "Senior Engineer"."""
    text = _DATE_RANGE_TEXT.sub(" ", text).strip(" -–—|,()")
    parts = [p.strip() for p in _TITLE_SEPARATORS.split(text) if p and p.strip()]
    if not parts:
        return None
    titled = [p for p in parts if any(w.lower().strip(".,") in TITLE_WORDS for w in p.split())]
    return (titled or parts)[0][:200]


def find_title(extracted: ExtractedText, name_line: Line | None, experience: list[Line], cities: CityList) -> str | None:
    lines = extracted.lines
    if name_line is not None and name_line in lines:
        index = lines.index(name_line)
        if index + 1 < len(lines):
            below = lines[index + 1]
            if below.page == name_line.page and looks_like_title(below.text, cities):
                return below.text[:200]
    for line in experience:
        text = line.text
        if text.lstrip().startswith(("-", "•", "*", "–")) or len(text.split()) > 12:
            continue
        if not _DATE_RANGE_TEXT.sub("", text).strip(" -–—|,()"):
            continue  # a line with only dates
        return role_from_experience_line(text)
    return None


# --- Years of experience ----------------------------------------------------------------------------

_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10,
           "nov": 11, "dec": 12}
_MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
_PRESENT = r"(?:present|current(?:ly)?|now|today|ongoing)"


def _date(prefix: str) -> str:
    return (rf"(?:(?P<{prefix}_month>{_MONTH})\s*,?\s*|(?P<{prefix}_num>\d{{1,2}})\s*[/.-]\s*)?"
            rf"(?P<{prefix}_year>(?:19|20)\d{{2}})")


# "Jan 2019 - Dec 2020", "01/2019 - Present", "2016 – 2018", and "Mar 2021 till date" (no separator).
DATE_RANGE = re.compile(rf"\b{_date('start')}\s*(?:(?:-|–|—|to|until|till|through)\s*"
                        rf"(?:{_date('end')}|(?P<present>{_PRESENT}))|(?P<till_date>till date|to date))\b", re.I)
EXPLICIT_YEARS = re.compile(
    r"(?P<n>\d{1,2}(?:\.\d{1,2})?)\s*\+?\s*(?:years?|yrs?)['’]?\s+(?:of\s+)?(?:[a-z-]+\s+){0,3}?(?:experience|exp)\b"
    r"|\bexperience\s+of\s+(?P<m>\d{1,2}(?:\.\d{1,2})?)\s*\+?\s*(?:years?|yrs?)\b", re.I)


def _month_index(month_name: str | None, month_number: str | None, year: str, *, is_end: bool) -> int | None:
    """Months since year 0. A year without a month means January for a start, December for an end."""
    if month_name:
        month = _MONTHS[month_name.lower()[:3]]
    elif month_number:
        month = int(month_number)
        if not 1 <= month <= 12:
            return None
    else:
        month = 12 if is_end else 1
    return int(year) * 12 + (month - 1)


def employment_ranges(lines: list[Line], today: date) -> list[tuple[int, int]]:
    """(start, end) month indexes, both months included. "Present" is today's month; the future is cut off."""
    now = today.year * 12 + (today.month - 1)
    ranges = []
    for line in lines:
        for m in DATE_RANGE.finditer(line.text):
            start = _month_index(m["start_month"], m["start_num"], m["start_year"], is_end=False)
            if m["present"] or m["till_date"]:
                end = now
            else:
                end = _month_index(m["end_month"], m["end_num"], m["end_year"], is_end=True)
            if start is None or end is None or start < 1950 * 12 or start > now:
                continue
            end = min(end, now)
            if start <= end:
                ranges.append((start, end))
    return ranges


def merged_months(ranges: list[tuple[int, int]]) -> int:
    """Total months covered, counting overlapping periods once.

    Jan 2018-Dec 2020 and Jan 2020-Dec 2022 overlap in 2020: merged they cover Jan 2018-Dec 2022,
    which is 60 months (5 years), not the 72 months a simple sum would give.
    """
    total, current = 0, None
    for start, end in sorted(ranges):
        if current and start <= current[1]:
            current = (current[0], max(current[1], end))
        else:
            if current:
                total += current[1] - current[0] + 1
            current = (start, end)
    if current:
        total += current[1] - current[0] + 1
    return total


def explicit_years(lines: list[Line]) -> Decimal | None:
    for line in lines:
        match = EXPLICIT_YEARS.search(line.text)
        if match:
            value = Decimal(match["n"] or match["m"])
            if value <= 60:
                return value
    return None


def years_of_experience(sections: dict[str, list[Line]], all_lines: list[Line], today: date) -> Decimal | None:
    """An explicit statement first (summary and header, then anywhere); otherwise merged date ranges."""
    preferred = sections.get("summary", []) + sections.get("header", [])
    explicit = explicit_years(preferred)
    if explicit is None:
        explicit = explicit_years(all_lines)
    if explicit is not None:  # "0 years of experience" is a real answer, so no truthiness test
        return explicit
    experience = sections.get("experience")
    if experience is None:  # no Experience heading: every date range except the education ones
        education = {id(line) for line in sections.get("education", [])}
        experience = [line for line in all_lines if id(line) not in education]
    months = merged_months(employment_ranges(experience, today))
    if months == 0:
        return None
    return (Decimal(months) / 12).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


# --- Education and summary --------------------------------------------------------------------------

_DEGREE_LONG = re.compile(
    r"\b(?:b\.?\s?tech|m\.?\s?tech|b\.?\s?sc|m\.?\s?sc|b\.?\s?com|m\.?\s?com|bca|mca|mba|ph\.?\s?d|bachelor\w*|"
    r"master\w*|doctor\w*|diploma|associate degree|hsc|ssc|higher secondary|senior secondary|12th|10th)\b", re.I)
_DEGREE_SHORT = re.compile(r"\b(?:B\.?E|M\.?E|B\.?S|M\.?S|B\.?A|M\.?A)\b\.?")  # case-sensitive: "be" is a verb
_INSTITUTION = re.compile(r"\b(?:universit\w*|institute|college|school|academy|iit|nit|iiit|iim|bits|polytechnic)\b", re.I)
_YEARS = re.compile(r"\b((?:19|20)\d{2})(?:\s*(?:-|–|—|to)\s*((?:19|20)\d{2}|present))?\b", re.I)
_EDU_SEPARATORS = re.compile(r"\s*(?:\||,|;|•|·|—|–|\s-\s)\s*")


def _tidy_part(text: str) -> str:
    """Trim spaces; remove a bracket only if it has no partner ("(2018" -> "2018", "(BE)" stays)."""
    text = text.strip()
    if text.count("(") != text.count(")"):
        text = text.strip("()").strip()
    return text


def _degree_match(text: str) -> bool:
    return bool(_DEGREE_LONG.search(text) or _DEGREE_SHORT.search(text))


_CONTINUES = re.compile(r"(?:\b(?:of|in|and|for|the|at)|[,&/-])$", re.I)


def _join_paragraph(texts: list[str]) -> str:
    """Lines of one paragraph: a wrapped line ("... University of" + "Mumbai, 2018") is joined with a
    space; a line that starts a new part ("M.Sc in Data Science" + "University of Mumbai") with " | "."""
    joined = texts[0]
    for text in texts[1:]:
        joined += (" " if _CONTINUES.search(joined) or text[:1].islower() else " | ") + text
    return joined


def _education_pieces(lines: list[Line]) -> list[str]:
    """One text per paragraph. A paragraph holding several entries is split where a degree follows a
    complete entry (one that already has an institution or a year); "Bachelor of Engineering (BE)"
    stays whole."""
    paragraphs: dict[tuple[int, int], list[str]] = {}
    for line in lines:
        paragraphs.setdefault((line.page, line.block), []).append(line.text.lstrip("-•*– ").strip())
    pieces = []
    for texts in paragraphs.values():
        joined = _join_paragraph(texts)
        starts = sorted({m.start() for m in _DEGREE_LONG.finditer(joined)} | {m.start() for m in _DEGREE_SHORT.finditer(joined)})
        cut = 0
        for start in starts:
            before = joined[cut:start]
            if start > cut and (_INSTITUTION.search(before) or _YEARS.search(before)):
                pieces.append(before.strip(" ,;|"))
                cut = start
        pieces.append(joined[cut:].strip(" ,;|"))
    return [piece for piece in pieces if piece]


def education_entries(lines: list[Line]) -> list[dict]:
    """{"degree", "institution", "years"} for each entry of the Education section (null if not found)."""
    entries: list[dict] = []
    current: dict = {}

    def push():
        if current.get("degree") or current.get("institution"):
            entries.append({key: current.get(key) for key in ("degree", "institution", "years")})

    for text in _education_pieces(lines):
        years_match = _YEARS.search(text)
        years = None
        if years_match:
            years = years_match.group(1) + (f"-{years_match.group(2).capitalize()}" if years_match.group(2) else "")
            text = (text[:years_match.start()] + " " + text[years_match.end():]).strip()
        parts = [_tidy_part(p) for p in _EDU_SEPARATORS.split(text) if _tidy_part(p)]
        degree = next((p for p in parts if _degree_match(p)), None)
        institution = next((p for p in parts if _INSTITUTION.search(p) and p != degree), None)
        if (degree and current.get("degree")) or (institution and current.get("institution") and not degree):
            push()
            current = {}
        if degree:
            current["degree"] = degree[:200]
        if institution:
            current["institution"] = institution[:200]
        if years and not current.get("years"):
            current["years"] = years
    push()
    return entries[:MAX_EDUCATION_ENTRIES]


def _shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def find_summary(sections: dict[str, list[Line]], all_lines: list[Line]) -> str | None:
    if sections.get("summary"):
        return _shorten(" ".join(line.text for line in sections["summary"]), MAX_SUMMARY_CHARS)
    # Header lines can hold an introduction when there is no Summary heading; the name, title and
    # contact lines are far shorter than a paragraph, so they never qualify.
    skip = {id(line) for line in sections.get("contact", [])}
    paragraphs: dict[tuple[int, int], list[str]] = {}
    for line in all_lines:
        if id(line) not in skip and heading_of(line.text)[0] is None and not is_contact(line.text):
            paragraphs.setdefault((line.page, line.block), []).append(line.text)
    for texts in paragraphs.values():  # dicts keep insertion order: the first paragraph comes first
        joined = " ".join(texts)
        if len(joined.split()) >= MIN_PARAGRAPH_WORDS:
            return _shorten(joined, MAX_SUMMARY_CHARS)
    return None


# --- Everything together ----------------------------------------------------------------------------


@dataclass
class CandidateFields:
    name: str
    email: str | None
    phone: str | None
    city: str | None
    current_title: str | None
    years_experience: Decimal | None
    education: list[dict]
    summary: str | None
    skills: list[str]
    unmatched_terms: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def extract_fields(extracted: ExtractedText, *, source_file: str, today: date,
                   cities: CityList | None = None) -> CandidateFields:
    """All candidate fields of one resume. `today` is the date "Present" stands for."""
    cities = cities or load_cities()
    lines = extracted.lines
    sections = split_sections(lines)
    contact = sections.get("header", []) + sections.get("contact", [])
    warnings: list[str] = []

    name_line = find_name(extracted, sections.get("header", []))
    if name_line is not None:
        name = _tidy_name(name_line.text)
    else:
        name = placeholder_name(source_file)
        warnings.append("name not found; the file name is used instead")

    email = find_email(contact) or find_email(lines)
    phone = find_phone(contact, lines)
    city = find_city(contact, lines, cities)
    skills_text = "\n".join(line.text for line in sections.get("skills", []))
    private = [*name.split(), email or "", (phone or "").lstrip("+"), city or ""]
    skills = extract_resume_skills(extracted.text, skills_text, extracted.table_cells, private_terms=private)

    return CandidateFields(
        name=name,
        email=email,
        phone=phone,
        city=city,
        current_title=find_title(extracted, name_line, sections.get("experience", []), cities),
        years_experience=years_of_experience(sections, lines, today),
        education=education_entries(sections.get("education", [])),
        summary=find_summary(sections, lines),
        skills=skills.skills,
        unmatched_terms=skills.unmatched,
        warnings=warnings,
    )
