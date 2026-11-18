"""Extractor plug-ins on saved pages (LLD §9.7): fields, links, the browser rule and malformed HTML."""

from datetime import UTC, datetime

import pytest

from app.crawler.pipeline import build_record
from app.extractors.registry import discover, get_registry
from tests.crawl_fakes import fixture

FAKE_JOBS = "https://realpython.github.io/fake-jobs/"
MOCK = "http://mock-site:8080"
FETCHED_AT = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)


def test_registry_discovers_every_plugin_file():
    assert sorted(e.name for e in discover()) == ["fake_python_jobs", "generic", "mock_dynamic", "mock_static"]


@pytest.mark.parametrize(
    ("url", "expected"),
    [(FAKE_JOBS, "fake_python_jobs"), (FAKE_JOBS + "jobs/x-0.html", "fake_python_jobs"),
     ("https://realpython.github.io/other/", "generic"), (f"{MOCK}/static/index.html", "mock_static"),
     (f"{MOCK}/dynamic/index.html", "mock_dynamic"), (f"{MOCK}/", "generic"), ("https://jobs.example.com/", "generic")],
)
def test_registry_selects_by_url(url, expected):
    assert get_registry().select(url).name == expected


def test_registry_honours_a_forced_extractor():
    assert get_registry().select(FAKE_JOBS, forced_name="generic").name == "generic"


# --- Fake Python Jobs (real saved pages) -----------------------------------------------------------


def test_fake_python_jobs_listing():
    result = get_registry().get("fake_python_jobs").parse(FAKE_JOBS, fixture("fake_python_jobs_listing.html"))
    assert len(result.jobs) == 100
    first = result.jobs[0]
    assert (first.title, first.company, first.location, first.posted_date) == (
        "Senior Python Developer", "Payne, Roberts and Davis", "Stewartbury, AA", "2021-04-08")
    assert first.apply_url == FAKE_JOBS + "jobs/senior-python-developer-0.html"
    assert len(result.links) == 100 and all(link.startswith(FAKE_JOBS + "jobs/") for link in result.links)


def test_fake_python_jobs_detail_and_record():
    url = FAKE_JOBS + "jobs/senior-python-developer-0.html"
    job = get_registry().get("fake_python_jobs").parse(url, fixture("fake_python_jobs_detail.html")).jobs[0]
    assert (job.title, job.location, job.posted_date, job.apply_url) == (
        "Senior Python Developer", "Stewartbury, AA", "2021-04-08", url)
    record = build_record(job, page_url=url, source="fake_python_jobs", fetched_at=FETCHED_AT).record
    assert record.dedup_key == url  # the listing card's Apply link: both merge into one job
    assert record.posted_date.isoformat() == "2021-04-08"
    # The (randomly generated) description mentions agile, CSS, Html, Python, Django and SCRUM.
    assert record.required_skills == ["Agile", "CSS", "Django", "HTML", "Python", "Scrum"]
    assert record.job_type == "unknown" and record.min_experience_years is None  # "no experience" is not a number


# --- Mock site ---------------------------------------------------------------------------------------


def test_mock_static_listing():
    result = get_registry().get("mock_static").parse(f"{MOCK}/static/index.html", fixture("mock_static_listing.html"))
    assert [j.title for j in result.jobs] == ["Backend Python Developer", "Frontend Engineer (React)", "Data Analyst"]
    assert result.jobs[2].salary_text == "$40 – $55 per hour"
    assert "/static/page-2.html" in result.links and "/private/internal.html" in result.links


def test_mock_static_detail_record():
    url = f"{MOCK}/static/jobs/backend-python-developer.html"
    job = get_registry().get("mock_static").parse(url, fixture("mock_static_detail.html")).jobs[0]
    record = build_record(job, page_url=url, source="mock_static", fetched_at=FETCHED_AT).record
    assert record.apply_url == record.dedup_key == "https://careers.example.com/jobs/backend-python-developer"
    assert (record.job_type, str(record.salary_min), str(record.salary_max), record.salary_currency, record.salary_period) == (
        "full_time", "900000", "1400000", "INR", "year")
    assert record.salary_text == "₹9,00,000 – ₹14,00,000 per year"
    assert str(record.min_experience_years) == "3" and record.posted_date.isoformat() == "2026-11-03"
    assert record.required_skills == ["Django", "FastAPI", "PostgreSQL", "Pytest", "Python"]
    assert record.nice_to_have_skills == ["Docker", "Kubernetes", "Redis"]  # "Docker is a plus" under Requirements


def test_mock_dynamic_needs_a_browser_only_before_rendering():
    extractor = get_registry().get("mock_dynamic")
    static = fixture("mock_dynamic_static.html")
    assert extractor.needs_browser(f"{MOCK}/dynamic/index.html", static)
    assert extractor.parse(f"{MOCK}/dynamic/index.html", static).jobs == []  # the server sends no jobs
    rendered = fixture("mock_dynamic_rendered.html")
    assert not extractor.needs_browser(f"{MOCK}/dynamic/index.html", rendered)


def test_mock_dynamic_rendered_snapshot():
    url = f"{MOCK}/dynamic/index.html"
    jobs = get_registry().get("mock_dynamic").parse(url, fixture("mock_dynamic_rendered.html")).jobs
    assert [j.title for j in jobs] == ["Full Stack Developer", "QA Automation Engineer", "Go Backend Engineer"]
    records = [build_record(j, page_url=url, source="mock_dynamic", fetched_at=FETCHED_AT).record for j in jobs]
    assert records[0].posted_date.isoformat() == "2026-11-16"  # "2 days ago", resolved against the fetch time
    assert records[0].is_remote and records[2].is_remote and not records[1].is_remote
    assert records[2].required_skills == ["Go", "Kafka", "PostgreSQL", "REST"]
    assert records[2].salary_min is None and records[2].salary_text is None


# --- Generic JSON-LD fallback and broken pages ---------------------------------------------------------

JSON_LD_PAGE = """<html><head>
<script type="application/ld+json">{ not valid json </script>
<script type="application/ld+json">{"@context": "https://schema.org", "@graph": [
  {"@type": "Organization", "name": "Ignored"},
  {"@type": "JobPosting", "title": "Data Engineer", "datePosted": "2026-11-01",
   "hiringOrganization": {"@type": "Organization", "name": "Globex"},
   "jobLocation": {"@type": "Place", "address": {"addressLocality": "Pune", "addressCountry": {"name": "India"}}},
   "employmentType": ["FULL_TIME"], "url": "/careers/data-engineer",
   "baseSalary": {"@type": "MonetaryAmount", "currency": "inr",
                  "value": {"@type": "QuantitativeValue", "minValue": 1500000, "maxValue": 2500000, "unitText": "YEAR"}},
   "skills": "Python, Apache Spark, Airflow", "experienceRequirements": {"monthsOfExperience": 36},
   "description": "&lt;p&gt;Build &lt;b&gt;pipelines&lt;/b&gt;.&lt;/p&gt;"}
]}</script></head><body><a href="/next">next</a></body></html>"""


def test_generic_extractor_reads_json_ld_job_postings():
    url = "https://jobs.example.com/list"
    result = get_registry().get("generic").parse(url, JSON_LD_PAGE)
    assert result.links == ["/next"] and len(result.jobs) == 1
    record = build_record(result.jobs[0], page_url=url, source="generic", fetched_at=FETCHED_AT).record
    assert (record.title, record.company, record.location, record.job_type) == ("Data Engineer", "Globex", "Pune, India", "full_time")
    assert record.apply_url == "https://jobs.example.com/careers/data-engineer"
    assert (record.salary_min, record.salary_max, record.salary_currency, record.salary_period) == (1500000, 2500000, "INR", "year")
    assert record.required_skills == ["Airflow", "Apache Spark", "Python"]  # structured skills come first
    assert record.min_experience_years == 3 and record.description == "Build pipelines."


@pytest.mark.parametrize("name", ["generic", "fake_python_jobs", "mock_static", "mock_dynamic"])
@pytest.mark.parametrize("html", ["", "<html><body><div class='card-content'><h2", "<<<>>>\x00 not html at all",
                                  "<article class='job-detail'></article>"])
def test_malformed_html_does_not_crash(name, html):
    result = get_registry().get(name).parse("http://mock-site:8080/static/x.html", html)
    assert isinstance(result.jobs, list) and isinstance(result.links, list)
