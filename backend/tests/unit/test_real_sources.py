"""Real job sources, offline: the Greenhouse and Lever job-board APIs, an official career page with
schema.org JobPosting data, JSON in the fetcher and crawler, and the demo-site guard (LLD §5.16).

The fixtures are saved responses in the documented formats, for invented companies:
tests/fixtures/json/greenhouse_jobs.json, lever_postings.json and html/careers_jsonld_academy.html.
"""

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.crawler.frontier import Crawler, CrawlSettings, SeedRejectedError
from app.crawler.pipeline import build_record
from app.extractors.base import BaseExtractor, ExtractionResult, RawJob
from app.extractors.registry import ExtractorRegistry, get_registry
from tests.crawl_fakes import FakeSite, MemorySink, fixture, html_page, json_fixture, make_fetcher

GREENHOUSE = "https://boards-api.greenhouse.io/v1/boards/contosogroup/jobs?content=true"
LEVER = "https://api.lever.co/v0/postings/fabrikam?mode=json"
ACADEMY = "https://careers.riverside-academy.test/"
NOW = datetime(2026, 11, 22, 9, 0, tzinfo=UTC)
JSON = {"content-type": "application/json; charset=utf-8"}


def records(source: str, url: str, body: str):
    """Parse a saved response and build the validated records, as the crawler does."""
    raw_jobs = get_registry().get(source).parse(url, body).jobs
    return {r.title: r for r in (build_record(raw, page_url=url, source=source, fetched_at=NOW).record for raw in raw_jobs)}


# --- Registry -------------------------------------------------------------------------------------


@pytest.mark.parametrize(("url", "expected"), [
    (GREENHOUSE, "greenhouse"), ("https://boards-api.greenhouse.io/v1/boards/acme/jobs", "greenhouse"),
    (LEVER, "lever"), ("https://boards.greenhouse.io/acme", "generic"), ("https://jobs.lever.co/acme", "generic"),
    (ACADEMY, "generic"),
])
def test_job_board_apis_are_selected_by_host(url, expected):
    assert get_registry().select(url).name == expected


def test_real_and_demo_sources():
    registry = get_registry()
    assert registry.demo_names == ["fake_python_jobs", "mock_dynamic", "mock_static"]
    assert {e.name for e in registry.extractors if not e.demo} == {"generic", "greenhouse", "lever"}
    assert [e.demo for e in registry.extractors] == sorted(e.demo for e in registry.extractors)  # real first
    assert all(e.label and e.description for e in registry.extractors)


@pytest.mark.parametrize(("url", "owner"), [
    ("http://mock-site:8080/static/index.html", "mock_static"), ("http://mock-site:8080/", "mock_static"),
    ("http://mock-site:8080/dynamic/index.html", "mock_static"), ("https://realpython.github.io/other/", "fake_python_jobs"),
    (GREENHOUSE, None), (ACADEMY, None),
])
def test_demo_sites_are_recognised_by_host(url, owner):
    site = get_registry().demo_site(url)
    if owner is None:
        assert site is None
    else:  # mock_static and mock_dynamic share the host; either one owns it
        assert site is not None and site.demo and site.handles_host(url)


def test_job_board_seed_templates():
    registry = get_registry()
    assert registry.get("greenhouse").seed_template.format(key="contosogroup") == GREENHOUSE
    assert registry.get("lever").seed_template.format(key="fabrikam") == LEVER
    assert registry.get("greenhouse").formats == registry.get("lever").formats == ("json",)
    assert registry.get("generic").formats == ("html",)


# --- Greenhouse -----------------------------------------------------------------------------------


def test_greenhouse_fields_from_the_job_board_api():
    jobs = records("greenhouse", GREENHOUSE, json_fixture("greenhouse_jobs.json"))
    assert list(jobs) == ["Senior Financial Analyst", "Registered Nurse, Occupational Health", "Mechanical Design Engineer",
                          "Backend Software Engineer", "Office Coordinator"]  # the job without a title is skipped
    analyst = jobs["Senior Financial Analyst"]
    assert (analyst.company, analyst.location, analyst.job_type, analyst.posted_date) == (
        "Contoso Group", "Pune, India", "full_time", date(2026, 11, 2))
    assert analyst.apply_url == analyst.dedup_key == "https://job-boards.greenhouse.io/contosogroup/jobs/4011001"
    assert analyst.source_url == GREENHOUSE and analyst.source == "greenhouse"
    assert analyst.min_experience_years == 3
    assert analyst.required_skills == ["Excel", "Financial Modeling", "GAAP"]
    assert analyst.nice_to_have_skills == ["IFRS", "Power BI"]
    assert "&lt;" not in analyst.description and "<p>" not in analyst.description  # unescaped, then plain text
    assert "Requirements" in analyst.description.splitlines()
    assert jobs["Mechanical Design Engineer"].job_type == "contract"  # from the "Employment Type" custom field
    assert jobs["Backend Software Engineer"].is_remote  # "Remote - India"
    assert jobs["Backend Software Engineer"].posted_date == date(2026, 11, 12)  # updated_at when first_published is null


def test_greenhouse_missing_fields_stay_unknown():
    coordinator = records("greenhouse", GREENHOUSE, json_fixture("greenhouse_jobs.json"))["Office Coordinator"]
    assert (coordinator.company, coordinator.location, coordinator.description, coordinator.posted_date) == (
        None, None, None, None)
    assert (coordinator.job_type, coordinator.min_experience_years, coordinator.salary_min) == ("unknown", None, None)
    assert coordinator.required_skills == coordinator.nice_to_have_skills == []


@pytest.mark.parametrize("body", ['{"jobs": "nope"}', "[]", '{"meta": {}}', '{"jobs": [null, 3, "x"]}'])
def test_greenhouse_unexpected_shapes_give_no_jobs(body):
    assert get_registry().get("greenhouse").parse(GREENHOUSE, body).jobs == []


def test_a_broken_json_body_fails_only_that_page():
    with pytest.raises(json.JSONDecodeError):
        get_registry().get("greenhouse").parse(GREENHOUSE, "<html>not json</html>")


# --- Lever ----------------------------------------------------------------------------------------


def test_lever_fields_from_the_postings_api():
    jobs = records("lever", LEVER, json_fixture("lever_postings.json"))
    assert list(jobs) == ["Growth Marketing Manager", "Account Executive, Mid-Market", "Supply Chain Planner",
                          "Corporate Paralegal", "Product Designer"]  # the posting without a title is skipped
    marketing = jobs["Growth Marketing Manager"]
    assert marketing.company is None  # Lever postings do not name the company; it is never guessed
    assert (marketing.location, marketing.job_type, marketing.posted_date, marketing.is_remote) == (
        "Bengaluru, India", "full_time", date(2026, 11, 3), False)  # hybrid is not remote
    assert (marketing.salary_min, marketing.salary_max, marketing.salary_currency, marketing.salary_period) == (
        Decimal("1800000.0"), Decimal("2600000.0"), "INR", "year")
    assert marketing.apply_url == "https://jobs.lever.co/fabrikam/5f1c2b3a-1111-4a2b-9c3d-000000000001"
    assert marketing.min_experience_years == 4
    assert marketing.required_skills == ["Digital Marketing", "Google Ads", "Google Analytics", "SEO"]
    assert marketing.nice_to_have_skills == ["Copywriting", "Email Marketing"]  # the "Nice to have" list
    assert jobs["Account Executive, Mid-Market"].is_remote  # workplaceType "remote"
    assert jobs["Corporate Paralegal"].job_type == "part_time"


def test_lever_missing_fields_stay_unknown_and_apply_url_is_the_fallback():
    designer = records("lever", LEVER, json_fixture("lever_postings.json"))["Product Designer"]
    assert designer.apply_url == "https://jobs.lever.co/fabrikam/5f1c2b3a-1111-4a2b-9c3d-000000000005/apply"
    assert (designer.location, designer.posted_date, designer.description, designer.salary_min) == (None, None, None, None)
    assert designer.job_type == "unknown"


@pytest.mark.parametrize("body", ['{"postings": []}', "[]", "[null, 1]"])
def test_lever_unexpected_shapes_give_no_jobs(body):
    assert get_registry().get("lever").parse(LEVER, body).jobs == []


# --- An official career page (schema.org JobPosting, the generic extractor) -----------------------


def test_career_page_with_jobposting_data():
    jobs = records("generic", ACADEMY, fixture("careers_jsonld_academy.html"))
    teacher = jobs["Mathematics Teacher (Grades 9-12)"]
    assert (teacher.company, teacher.job_type, teacher.posted_date, teacher.min_experience_years) == (
        "Riverside Academy", "full_time", date(2026, 11, 4), Decimal("2.0"))
    assert (teacher.salary_min, teacher.salary_max, teacher.salary_period) == (Decimal("600000.0"), Decimal("900000.0"), "year")
    assert teacher.apply_url == "https://careers.riverside-academy.test/jobs/maths-teacher"
    assert teacher.nice_to_have_skills == ["Curriculum Development"]
    assert jobs["HR Generalist"].job_type == "part_time"
    assert jobs["Data Analyst"].is_remote and jobs["Data Analyst"].required_skills == ["Data Analysis", "SQL", "Tableau"]


# --- Fetcher and crawler: JSON responses -------------------------------------------------------------


def test_the_fetcher_accepts_json_and_says_so():
    site = FakeSite({GREENHOUSE: (200, json_fixture("greenhouse_jobs.json"), JSON)})
    fetcher, _, _ = make_fetcher(site, allowed=("boards-api.greenhouse.io",))
    result = fetcher.fetch_page(GREENHOUSE)
    assert (result.outcome, result.content_type) == ("ok", "application/json")


def board_crawl(site, seed, allowed, extractor=None, registry=None):
    fetcher, _, _ = make_fetcher(site, allowed=allowed)
    sink = MemorySink()
    crawler = Crawler(CrawlSettings(seed, 1, 5, list(allowed), extractor), fetcher, registry or get_registry(), sink,
                      renderer_factory=lambda: None, sleep=lambda s: None)
    return crawler.run(), sink


def test_a_greenhouse_board_is_crawled_in_one_request():
    site = FakeSite({GREENHOUSE: (200, json_fixture("greenhouse_jobs.json"), JSON)},
                    robots={"https://boards-api.greenhouse.io": "User-agent: *\nDisallow: /embed/\n"})
    stats, sink = board_crawl(site, GREENHOUSE, ("boards-api.greenhouse.io",))
    assert (stats.pages_processed, stats.pages_succeeded, stats.jobs_extracted) == (1, 1, 5)
    assert {r.record.source for r in sink.saved} == {"greenhouse"}
    assert site.page_requests() == [GREENHOUSE]


def test_robots_txt_still_applies_to_a_job_board():
    site = FakeSite({GREENHOUSE: (200, json_fixture("greenhouse_jobs.json"), JSON)},
                    robots={"https://boards-api.greenhouse.io": "User-agent: *\nDisallow: /v1/\n"})
    with pytest.raises(SeedRejectedError, match="robots.txt"):
        board_crawl(site, GREENHOUSE, ("boards-api.greenhouse.io",))
    assert site.page_requests() == []


def test_json_is_skipped_by_an_extractor_that_reads_html():
    site = FakeSite({"https://jobs.example.com/feed": (200, '{"jobs": []}', JSON)})
    stats, sink = board_crawl(site, "https://jobs.example.com/feed", ("jobs.example.com",))
    assert (stats.pages_skipped, stats.pages_succeeded) == (1, 0)
    assert "Skipped https://jobs.example.com/feed: JSON content, which the generic extractor does not read" in \
        sink.log.messages("INFO")


class _EveryPageHasAJob(BaseExtractor):
    """A real-source extractor that finds a job anywhere, to show what the demo-site guard drops."""

    name = "everywhere"

    def parse(self, url, html):
        return ExtractionResult(jobs=[RawJob(title="Invented job", apply_url=url + "#job")], links=[])


def test_jobs_on_a_demo_site_are_dropped_unless_its_demo_extractor_finds_them():
    seed = "http://mock-site:8080/board.html"
    site = FakeSite({seed: html_page("<p>A demo page</p>")})
    registry = ExtractorRegistry([_EveryPageHasAJob(), *get_registry().extractors])
    stats, sink = board_crawl(site, seed, ("mock-site",), extractor="everywhere", registry=registry)
    assert sink.saved == [] and stats.jobs_extracted == 1
    assert any(m.startswith(f"Dropped 1 jobs found on {seed} by the everywhere extractor: it is a demo site")
               for m in sink.log.messages("WARNING"))


def test_jobs_found_by_the_demo_extractor_on_its_site_are_kept_as_demo():
    seed = "http://mock-site:8080/static/index.html"
    site = FakeSite({seed: fixture("mock_static_listing.html")})
    stats, sink = board_crawl(site, seed, ("mock-site",))
    assert sink.saved and {r.record.source for r in sink.saved} == {"mock_static"}
    assert not sink.log.messages("WARNING")
