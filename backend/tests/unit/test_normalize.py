"""Normalization of extracted values and JobRecord validation (LLD §5.17, HLD §11.8)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.crawler.normalize import (
    clean_description,
    detect_remote,
    extract_min_experience,
    make_dedup_key,
    map_job_type,
    parse_posted_date,
    parse_salary,
)
from app.crawler.pipeline import build_record
from app.extractors.base import RawJob
from app.schemas.job import JobRecord

FETCHED_AT = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("2021-04-08", date(2021, 4, 8)), ("2026-11-03T10:15:00Z", date(2026, 11, 3)), ("3 Nov 2026", date(2026, 11, 3)),
     ("Apr 8, 2021", date(2021, 4, 8)), ("April 8 2021", date(2021, 4, 8)), ("Posted: 8 April 2021", date(2021, 4, 8)),
     ("today", date(2026, 11, 18)), ("yesterday", date(2026, 11, 17)), ("3 days ago", date(2026, 11, 15)),
     ("2 weeks ago", date(2026, 11, 4)), ("1 month ago", date(2026, 10, 19)), ("5 hours ago", date(2026, 11, 18)),
     ("someday", None), ("", None), (None, None), ("1850-01-01", None)],
)
def test_posted_dates_become_iso_dates(raw, expected):
    assert parse_posted_date(raw, FETCHED_AT) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("₹9,00,000 – ₹14,00,000 per year", ("900000", "1400000", "INR", "year")),
     ("$40 – $55 per hour", ("40", "55", "USD", "hour")),
     ("₹25,000 per month", ("25000", "25000", "INR", "month")),
     ("12 LPA", ("1200000", "1200000", "INR", "year")),
     ("$80k - $100k a year", ("80000", "100000", "USD", "year")),
     ("€50,000/yr", ("50000", "50000", "EUR", "year")),
     ("40 hours a week, competitive pay", ("40", "40", None, "week")),
     ("Competitive, based on experience", (None, None, None, None))],
)
def test_salaries_become_numbers(text, expected):
    salary = parse_salary(text)
    got = tuple(None if v is None else str(v) for v in (salary.min, salary.max)) + (salary.currency, salary.period)
    assert got == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Full-time", "full_time"), ("FULL_TIME", "full_time"), ("Permanent", "full_time"), ("part time", "part_time"),
     ("Contract", "contract"), ("CONTRACTOR", "contract"), ("Freelance", "contract"), ("Internship", "internship"),
     ("INTERN", "internship"), ("Temporary", "temporary"), ("Volunteer", "unknown"), (None, "unknown")],
)
def test_job_types_map_to_the_allowed_values(raw, expected):
    assert map_job_type(raw) == expected


def test_remote_detection():
    assert detect_remote("Remote (India)") and detect_remote(None, "Developer - Work From Home")
    assert not detect_remote("Pune, India", "Backend Developer") and not detect_remote("Remotely located office")


@pytest.mark.parametrize(
    ("text", "expected"),
    [("3+ years of professional experience with Python", Decimal("3")), ("At least 2 years of experience", Decimal("2")),
     ("3-5 years experience", Decimal("3")), ("Minimum 1.5 yrs of experience", Decimal("1.5")),
     ("no experience needed", None), ("Python 3 for 2 hours a day", None)],
)
def test_minimum_experience(text, expected):
    assert extract_min_experience(text) == expected


def test_descriptions_lose_html_and_extra_whitespace():
    assert clean_description("<p>Build   <b>APIs</b></p><ul><li>Python</li><li>SQL</li></ul>") == "Build APIs\n- Python\n- SQL"
    assert clean_description("  line one  \n\n\tline   two ") == "line one\nline two"
    assert clean_description("&lt;p&gt;escaped&lt;/p&gt;") == "escaped"
    assert clean_description("   ") is None


def test_dedup_key_is_the_apply_url_or_a_stable_hash():
    assert make_dedup_key("https://jobs.example.com/1", "s", "t", "c", "l") == "https://jobs.example.com/1"
    first = make_dedup_key(None, "site", "Data  Analyst", "Acme", "Pune")
    assert first == make_dedup_key(None, "site", "data analyst", "ACME", "pune") and first.startswith("sha256:")
    assert first != make_dedup_key(None, "site", "Data Analyst", "Acme", "Mumbai")


# --- JobRecord ---------------------------------------------------------------------------------------

VALID = dict(title="Developer", apply_url="https://jobs.example.com/1", source="test",
             source_url="https://jobs.example.com/1", dedup_key="https://jobs.example.com/1")


def test_valid_record_keeps_numbers_as_numbers():
    record = JobRecord(**VALID, salary_min="1000", salary_max=2000.5, min_experience_years="2", posted_date="2026-11-03")
    assert record.salary_min == Decimal("1000") and isinstance(record.salary_max, Decimal)
    assert record.posted_date == date(2026, 11, 3)


@pytest.mark.parametrize(
    "changes",
    [{"title": ""}, {"apply_url": "/relative/path"}, {"apply_url": "ftp://jobs.example.com/x"}, {"source_url": "not a url"},
     {"salary_min": 5, "salary_max": 1}, {"salary_min": -1}, {"salary_currency": "rupees"}, {"salary_period": "decade"},
     {"job_type": "gig"}, {"min_experience_years": 80}, {"posted_date": "yesterday"},
     {"required_skills": ["Python"], "nice_to_have_skills": ["Python"]}, {"unexpected": 1}],
)
def test_invalid_records_are_rejected(changes):
    with pytest.raises(ValidationError):
        JobRecord(**{**VALID, **changes})


def test_build_record_normalizes_a_raw_job():
    raw = RawJob(title="  Python   Developer ", company="Acme", location="Remote", job_type="Part-time",
                 salary_text="$30 - $40 per hour", posted_date="3 days ago", apply_url="/apply/7",
                 description="<h3>Requirements</h3><ul><li>2+ years of experience with Flask</li></ul>")
    built = build_record(raw, page_url="https://jobs.example.com/list", source="test", fetched_at=FETCHED_AT)
    r = built.record
    assert (r.title, r.job_type, r.is_remote, r.apply_url) == ("Python Developer", "part_time", True, "https://jobs.example.com/apply/7")
    assert (r.salary_min, r.salary_max, r.salary_currency, r.salary_period) == (30, 40, "USD", "hour")
    assert (r.posted_date, r.min_experience_years, r.required_skills) == (date(2026, 11, 15), 2, ["Flask"])
    assert built.skills_known and built.warnings == []


def test_build_record_falls_back_to_the_page_url_and_warns_about_bad_dates():
    built = build_record(RawJob(title="Analyst", apply_url="mailto:hr@example.com", posted_date="soon"),
                         page_url="https://jobs.example.com/a", source="test", fetched_at=FETCHED_AT)
    assert built.record.apply_url == "https://jobs.example.com/a"
    assert built.record.posted_date is None and "unrecognized posted date" in built.warnings[0]
    assert not built.skills_known  # no description: existing skill links must not be replaced


def test_build_record_without_a_title_is_invalid():
    with pytest.raises(ValidationError):
        build_record(RawJob(company="Acme"), page_url="https://jobs.example.com/a", source="test", fetched_at=FETCHED_AT)
