"""Candidate field extraction and CandidateRecord validation (LLD §6.6-6.7, §9.7).

Dates are fixed: "today" is 18 November 2026, so "Present" never changes the expected values.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.resumes.fields import (
    education_entries,
    employment_ranges,
    extract_fields,
    find_phone,
    heading_of,
    merged_months,
    normalize_phone,
    role_from_experience_line,
    split_sections,
    years_of_experience,
)
from app.resumes.text_extraction import ExtractedText, Line, PageText
from app.schemas.candidate import RecordInvalid, validate_candidate

TODAY = date(2026, 11, 18)


def resume(text: str, source: str = "text") -> ExtractedText:
    """Lines of text on page 1. "# " marks a large-font line (22 pt); a blank line ends a paragraph."""
    lines, block, top = [], 0, 40.0
    for raw in text.strip("\n").splitlines():
        if not raw.strip():
            block += 1
            continue
        big = raw.startswith("# ")
        size = 0.0 if source == "ocr" else (22.0 if big else 10.0)
        lines.append(Line(raw[2:] if big else raw.strip(), 1, block=block, size=size, top=top))
        top += 14
    return ExtractedText([PageText(1, 842.0, source, lines)])


def lines_of(text: str) -> list[Line]:
    return resume(text).lines


def fields(text: str, source: str = "text", source_file: str = "cv_01.pdf"):
    return extract_fields(resume(text, source), source_file=source_file, today=TODAY)


SAMPLE = """
Curriculum Vitae
# Asha Verma
Senior Backend Engineer
Bangalore, India | asha.verma@example.com | Mobile: +91 98765 43210

Professional Summary
Backend engineer building APIs and data pipelines for analytics products.

Work Experience
Senior Backend Engineer, Acme Analytics (Jan 2020 - Present)
- Built REST APIs with FastAPI and PostgreSQL
Software Engineer | Globex Systems | Jun 2017 - Mar 2020

Education
B.Tech in Computer Engineering, Savitribai Phule Pune University, 2013 - 2017

Technical Skills
Python, Go, Docker, C++, C#, .NET, Node.js
"""


def test_a_typical_resume():
    f = fields(SAMPLE)
    assert (f.name, f.email, f.phone, f.city) == ("Asha Verma", "asha.verma@example.com", "+919876543210", "Bengaluru")
    assert f.current_title == "Senior Backend Engineer"
    assert f.years_experience == Decimal("9.5")  # Jun 2017 - Nov 2026, the two jobs merged
    assert f.education == [{"degree": "B.Tech in Computer Engineering",
                            "institution": "Savitribai Phule Pune University", "years": "2013-2017"}]
    assert f.summary == "Backend engineer building APIs and data pipelines for analytics products."
    assert f.skills == [".NET", "C#", "C++", "Docker", "FastAPI", "Go", "Node.js", "PostgreSQL", "Python", "REST"]
    assert f.warnings == []


# --- Sections ---------------------------------------------------------------------------------------

@pytest.mark.parametrize(("text", "section"), [
    ("Summary", "summary"), ("PROFILE", "summary"), ("About Me:", "summary"),
    ("Work Experience", "experience"), ("Employment History", "experience"), ("Professional Experience", "experience"),
    ("Education", "education"), ("Academic Qualifications", "education"),
    ("Skills", "skills"), ("Technical Skills", "skills"), ("Skills & Tools", "skills"), ("KEY SKILLS", "skills"),
    ("Projects", "other"), ("Certifications", "other"), ("Contact Details", "contact"),
])
def test_heading_variations(text, section):
    assert heading_of(text) == (section, "")


def test_an_inline_heading_keeps_its_content():
    assert heading_of("Skills: Python, Go, Docker") == ("skills", "Python, Go, Docker")


@pytest.mark.parametrize("text", ["Built the skills matrix for the team", "Experience with large systems matters",
                                  "Education technology startup"])
def test_ordinary_lines_are_not_headings(text):
    assert heading_of(text) == (None, "")


def test_lines_before_the_first_heading_are_the_header():
    sections = split_sections(lines_of("# Jane Doe\nPune\nSkills\nPython"))
    assert [l.text for l in sections["header"]] == ["Jane Doe", "Pune"]
    assert [l.text for l in sections["skills"]] == ["Python"]


# --- Name -------------------------------------------------------------------------------------------

def test_the_name_is_the_largest_font_near_the_top():
    assert fields("Curriculum Vitae\nSoftware Engineer\n# Ravi Shah\nravi@example.com").name == "Ravi Shah"


def test_ocr_text_uses_the_first_header_line_that_is_not_contact_information():
    text = "RESUME\nravi.shah@example.com | +91 90000 11111\nRAVI SHAH\nData Engineer\nSkills\nPython"
    assert fields(text, source="ocr").name == "Ravi Shah"  # all-capital names are tidied


def test_without_a_name_the_file_name_is_used_with_a_warning():
    f = fields("ravi@example.com\nSkills\nPython, SQL", source_file="cv_07_final.pdf")
    assert f.name == "cv 07 final"
    assert f.warnings == ["name not found; the file name is used instead"]


# --- Contact details -------------------------------------------------------------------------------

@pytest.mark.parametrize(("raw", "normalized"), [
    ("+91 98765 43210", "+919876543210"), ("(+91) 98765-43210", "+919876543210"),
    ("+1 (555) 010-9999", "+15550109999"), ("098765 43210", "09876543210"), ("020.1234.5678", "02012345678"),
])
def test_phone_numbers_are_normalized_to_digits_with_an_optional_plus(raw, normalized):
    assert normalize_phone(raw) == normalized


def test_an_unlabelled_number_must_look_like_a_phone_number():
    assert find_phone(lines_of("Pune | 2015 - 2019"), []) is None
    assert find_phone(lines_of("Pune | +91 98765 43210"), []) == "+919876543210"


def test_a_labelled_malformed_phone_is_kept_for_validation():
    assert find_phone([], lines_of("Phone: 12345")) == "12345"


def test_the_city_comes_from_contact_or_location_lines_only():
    """The city list itself is tested in test_locations.py; here, which lines are searched."""
    text = "# Ravi Shah\nravi@example.com\nExperience\nEngineer, Acme, Mumbai office\nLocation: Pune"
    assert fields(text).city == "Pune"


# --- Current title ----------------------------------------------------------------------------------

def test_the_title_falls_back_to_the_first_role_in_experience():
    text = "# Ravi Shah\nravi@example.com | Pune\nExperience\nJan 2019 - Present\nData Engineer at Initech\n- Built pipelines"
    assert fields(text).current_title == "Data Engineer"


def test_a_long_entry_line_gives_the_role_and_a_wrapped_bullet_line_is_never_a_title():
    """Regression: a role line with company, place and dates has many tokens, and the next bullet wraps
    onto a line without a bullet mark. The role must come from the entry line, never from the wrapped text."""
    text = ("# Ravi Shah\nravi@example.com | +91 98765 43210 | linkedin.com/in/ravishah\nExperience\n"
            "Initech Pvt. Ltd. - Data Analyst Intern | Nagpur, Maharashtra | May 2025 - Jun 2025\n"
            "• Built a classifier for warehouse photos that sorts every image\n"
            "into Boxes, Pallets, Shelves, and Empty classes.")
    assert fields(text).current_title == "Data Analyst Intern"


def test_a_wrapped_line_is_skipped_even_without_an_entry_line():
    text = "# Ravi Shah\nravi@example.com\nExperience\n• Built dashboards for the finance team and\nmigrated reports to Power BI."
    assert fields(text).current_title is None


def test_cities_of_education_and_experience_entries_are_not_the_candidate_city():
    """Regression: with no city in the contact lines or a Location line, the city stays unknown. A university
    or internship location is not where the candidate lives, so it is never guessed from those lines."""
    text = ("# Ravi Shah\nravi@example.com | +91 98765 43210\nEducation\n"
            "Sample Institute of Technology - B.Tech | Jaipur, Rajasthan | 2022 - 2026\nExperience\n"
            "Initech Pvt. Ltd. - Data Intern | Nagpur, Maharashtra | May 2025 - Jun 2025")
    assert fields(text).city is None


def test_a_location_under_the_name_is_not_a_title():
    text = "# Ravi Shah\nPune, India\nExperience\nQA Engineer, Hooli (2020 - 2023)"
    assert fields(text).current_title == "QA Engineer"


@pytest.mark.parametrize(("line", "role"), [
    ("Senior Engineer, Acme Corp (Jan 2019 - Present)", "Senior Engineer"),
    ("Acme Corp | Backend Developer | 2019 - 2021", "Backend Developer"),
    ("Data Analyst at Initech", "Data Analyst"),
    ("Freelance work", "Freelance work"),
])
def test_role_from_an_experience_line(line, role):
    assert role_from_experience_line(line) == role


# --- Years of experience ----------------------------------------------------------------------------

def test_overlapping_ranges_are_merged_the_lld_example():
    """Jan 2018 - Dec 2020 and Jan 2020 - Dec 2022 overlap in 2020: 5 years, not 6 (LLD §6.6)."""
    ranges = employment_ranges(lines_of("Jan 2018 – Dec 2020\nJan 2020 – Dec 2022"), TODAY)
    assert merged_months(ranges) == 60
    sections = split_sections(lines_of("Experience\nDev, A (Jan 2018 – Dec 2020)\nDev, B (Jan 2020 – Dec 2022)"))
    assert years_of_experience(sections, [], TODAY) == Decimal("5.0")


def test_present_means_the_given_date():
    sections = split_sections(lines_of("Experience\nEngineer (Jan 2019 - Present)"))
    assert years_of_experience(sections, [], TODAY) == Decimal("7.9")                # Jan 2019 - Nov 2026: 95 months
    assert years_of_experience(sections, [], date(2026, 12, 31)) == Decimal("8.0")  # a later "today": 96 months


@pytest.mark.parametrize(("text", "months"), [
    ("January 2019 to March 2019", 3), ("01/2019 - 12/2019", 12), ("2016 – 2018", 36), ("Sept 2020 – Current", 75),
    ("Mar 2021 till date", 69), ("2019-Present", 95), ("Jun 2025 - Dec 2030", 18),  # the future is cut off at today
    ("13/2019 - 12/2019", 0),  # not a month
])
def test_date_range_formats(text, months):
    assert merged_months(employment_ranges(lines_of(text), TODAY)) == months


def test_contained_and_separate_ranges():
    ranges = employment_ranges(lines_of("Jan 2010 - Dec 2019\nJun 2012 - Jun 2013\nJan 2022 - Dec 2022"), TODAY)
    assert merged_months(ranges) == 120 + 12  # the contained job adds nothing; the separate one adds a year


def test_an_explicit_statement_is_preferred():
    text = "Summary\nAnalyst with 6+ years of experience in retail.\nExperience\nAnalyst (Jan 2024 - Present)"
    sections = split_sections(lines_of(text))
    assert years_of_experience(sections, lines_of(text), TODAY) == Decimal("6")


@pytest.mark.parametrize(("sentence", "years"), [
    ("over 7 years of professional experience", "7"), ("3.5 yrs exp in testing", "3.5"),
    ("10+ years' experience", "10"), ("an experience of 4 years", "4"), ("0 years of experience", "0"),
])
def test_explicit_statement_forms(sentence, years):
    sections = split_sections(lines_of(f"Summary\n{sentence}"))
    assert years_of_experience(sections, [], TODAY) == Decimal(years)


def test_education_dates_do_not_count_as_experience():
    text = "Education\nB.Tech, Pune University, 2013 - 2017\nProjects\nChat app (2018 - 2019)"
    lines = lines_of(text)
    assert years_of_experience(split_sections(lines), lines, TODAY) == Decimal("2.0")  # only the 2018-2019 range


def test_no_dates_means_unknown_experience():
    lines = lines_of("Experience\nIntern at a startup")
    assert years_of_experience(split_sections(lines), lines, TODAY) is None


# --- Education and summary --------------------------------------------------------------------------

def test_education_entries():
    text = ("Education\nM.Sc in Data Science\nUniversity of Mumbai | 2019 - 2021\n\n"
            "B.E. in Information Technology, Anna University, 2018\n\nHSC, Fergusson College, 2014")
    assert education_entries(split_sections(lines_of(text))["education"]) == [
        {"degree": "M.Sc in Data Science", "institution": "University of Mumbai", "years": "2019-2021"},
        {"degree": "B.E. in Information Technology", "institution": "Anna University", "years": "2018"},
        {"degree": "HSC", "institution": "Fergusson College", "years": "2014"},
    ]


def test_a_degree_name_with_an_abbreviation_stays_one_entry():
    lines = split_sections(lines_of("Education\nBachelor of Engineering (BE), Pune University, 2018"))["education"]
    assert education_entries(lines) == [
        {"degree": "Bachelor of Engineering (BE)", "institution": "Pune University", "years": "2018"}]


def test_without_a_summary_section_the_first_paragraph_is_used():
    text = ("# Ravi Shah\nravi@example.com\n\nI build data platforms for retail companies and enjoy turning messy\n"
            "logs into clean, trustworthy tables for analysts.\n\nSkills\nPython")
    assert fields(text).summary.startswith("I build data platforms for retail companies")


def test_missing_optional_fields_are_none():
    f = fields("# Ravi Shah\nSkills\nPython")
    assert (f.email, f.phone, f.city, f.current_title, f.years_experience, f.summary, f.education) == (
        None, None, None, None, None, None, [])


# --- Skills -----------------------------------------------------------------------------------------

def test_ambiguous_words_count_only_in_a_skill_context():
    text = ("# Ravi Shah\nSummary\nI go to meetups, lead R&D work, and help the rest of the team ship.\n"
            "Skills\nGo\nR\nSwift")
    assert fields(text).skills == ["Go", "R", "Swift"]
    assert fields("# Ravi Shah\nSummary\nI go to meetups and lead R&D work with the rest of the team.").skills == []


def test_unmatched_skill_terms_never_include_personal_details():
    text = "# Ravi Shah\nravi@example.com\nSkills\nPython, Shah Toolkit, ravi@example.com, 98765, Looker Studio"
    assert fields(text).unmatched_terms == ["looker studio"]  # the name, the email and the number are dropped


# --- CandidateRecord --------------------------------------------------------------------------------

VALID = {"name": "Asha Verma", "source_file": "cv.pdf", "parsed_with_ocr": False, "file_sha256": "a" * 64,
         "stored_path": "x.pdf", "resume_text": "Some resume text"}


@pytest.mark.parametrize(("field", "value", "warning"), [
    ("email", "asha@example", "invalid email removed"),
    ("phone", "12345", "invalid phone removed"),
    ("years_experience", -2, "invalid years experience removed"),
    ("current_title", "x" * 300, "invalid current title removed"),
])
def test_an_invalid_optional_field_becomes_null_with_a_warning(field, value, warning):
    record = validate_candidate({**VALID, field: value, "city": "Pune"})
    assert getattr(record, field) is None and record.city == "Pune"
    assert record.parse_warnings == [warning]


def test_several_invalid_optional_fields_are_all_removed():
    record = validate_candidate({**VALID, "email": "nope", "phone": "1", "parse_warnings": ["earlier note"]})
    assert (record.email, record.phone) == (None, None)
    assert record.parse_warnings == ["earlier note", "invalid email removed", "invalid phone removed"]


def test_an_invalid_required_field_names_the_field_but_never_the_value():
    with pytest.raises(RecordInvalid) as excinfo:
        validate_candidate({**VALID, "resume_text": "", "email": "secret.person@example.com"})
    assert excinfo.value.fields == ["resume_text"]
    assert "secret.person" not in str(excinfo.value)
