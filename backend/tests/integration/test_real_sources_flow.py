"""Real job sources end to end, against PostgreSQL: API -> crawl task -> extractor -> jobs table -> search,
detail, exports and matching (LLD §5.16-5.18).

The job boards are saved responses served by httpx.MockTransport (no internet): a Greenhouse
board, a Lever board and an official career page with schema.org JobPosting data, all for invented
companies. The demo mock site runs next to them, so real and demo jobs can be compared. Automatic
re-matching is switched off here; match runs start only when a test asks. The people are invented.
"""

import csv
import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import get_settings
from app.crawler import browser, fetcher
from app.db.session import SessionLocal
from app.main import app
from app.matching.engine import load_inputs
from app.matching.scoring import Weights, score_pair
from app.models import Job, Match
from app.services import background_jobs as service
from app.worker.celery_app import celery_app
from tests.crawl_fakes import FakeRenderer, fixture, json_fixture
from tests.integration.test_crawl_flow import ORIGIN as MOCK, SEED as MOCK_SEED, mock_site
from tests.integration.test_match_flow import add_candidate

GREENHOUSE = "https://boards-api.greenhouse.io/v1/boards/contosogroup/jobs?content=true"
LEVER = "https://api.lever.co/v0/postings/fabrikam?mode=json"
ACADEMY = "https://careers.riverside-academy.test/"
JSON = {"content-type": "application/json; charset=utf-8"}
ROBOTS = {
    "https://boards-api.greenhouse.io": "User-agent: *\nDisallow: /embed/\n",  # as published by the real host
    "https://api.lever.co": "User-agent: *\nAllow: /\nCrawl-delay: 1\n",
}


def site(**overrides):
    """The mock site plus the three real-source fixtures, on their own hosts."""
    pages = {GREENHOUSE: (200, json_fixture("greenhouse_jobs.json"), JSON),
             LEVER: (200, json_fixture("lever_postings.json"), JSON),
             ACADEMY: fixture("careers_jsonld_academy.html"), **overrides.pop("pages", {})}
    return mock_site(pages=pages, robots={**ROBOTS, **overrides.pop("robots", {})}, **overrides)


@pytest.fixture
def boards(app_db, fast_crawler, monkeypatch):
    """Crawl and match tasks run at once, against state["site"]."""
    state = {"site": site()}
    monkeypatch.setattr(fetcher, "create_client", lambda timeout: state["site"].client())
    monkeypatch.setattr(browser, "BrowserRenderer", lambda **kwargs: FakeRenderer(
        {f"{MOCK}/dynamic/index.html": fixture("mock_dynamic_rendered.html")}))
    monkeypatch.setattr(service, "publish_task", lambda name, job_id: celery_app.tasks[name].apply(args=[str(job_id)]).id)
    monkeypatch.setattr(service, "revoke_task", lambda task_id: None)
    monkeypatch.setattr(get_settings(), "auto_rematch", False)  # no automatic match runs in these tests
    state["api"] = TestClient(app)
    return state


def crawl(state, seed: str, **extra) -> dict:
    response = state["api"].post("/background-jobs/crawl", json={"seed_url": seed, "max_depth": 1, "max_pages": 30, **extra})
    assert response.status_code == 202, response.text
    detail = state["api"].get(f"/background-jobs/{response.json()['background_job_id']}").json()
    assert detail["status"] == "completed", detail
    return detail


def jobs(state, **query) -> dict[str, dict]:
    body = state["api"].get("/jobs", params={"page_size": 100, **query}).json()
    return {item["title"]: item for item in body["items"]}


def total(state, **query) -> int:
    return state["api"].get("/jobs", params={"page_size": 1, **query}).json()["total"]


# --- Each real source, through the API ----------------------------------------------------------------


def test_a_greenhouse_board_through_the_api(boards):
    crawl(boards, GREENHOUSE)
    found = jobs(boards, source="greenhouse")
    assert set(found) == {"Senior Financial Analyst", "Registered Nurse, Occupational Health", "Mechanical Design Engineer",
                          "Backend Software Engineer", "Office Coordinator"}
    assert {j["listing"] for j in found.values()} == {"real"}
    assert {title: j["industry"] for title, j in found.items()} == {
        "Senior Financial Analyst": "finance_banking", "Registered Nurse, Occupational Health": "healthcare",
        "Mechanical Design Engineer": "engineering", "Backend Software Engineer": "software_it",
        "Office Coordinator": "other"}
    nurse = boards["api"].get(f"/jobs/{found['Registered Nurse, Occupational Health']['job_id']}").json()
    assert nurse["apply_url"] == "https://job-boards.greenhouse.io/contosogroup/jobs/4011002"  # the original posting
    assert nurse["source_url"] == GREENHOUSE and nurse["company"] == "Contoso Group"
    assert nurse["industry_reasons"][0] == 'Title: "nurse" (+3)'
    assert nurse["required_skills"] == ["ACLS", "BLS", "Electronic Health Records", "Patient Care"]
    coordinator = boards["api"].get(f"/jobs/{found['Office Coordinator']['job_id']}").json()
    assert (coordinator["company"], coordinator["location"], coordinator["description"], coordinator["posted_date"],
            coordinator["salary"], coordinator["min_experience_years"]) == (None, None, None, None, None, None)
    assert coordinator["industry_reasons"] == ["No industry terms in the title, skills or description."]


def test_a_lever_board_through_the_api(boards):
    crawl(boards, LEVER)
    found = jobs(boards, source="lever")
    assert {title: j["industry"] for title, j in found.items()} == {
        "Growth Marketing Manager": "marketing", "Account Executive, Mid-Market": "sales_business",
        "Supply Chain Planner": "operations_supply_chain", "Corporate Paralegal": "legal", "Product Designer": "design"}
    marketing = found["Growth Marketing Manager"]
    assert marketing["salary"] == {"min": 1800000, "max": 2600000, "currency": "INR", "period": "year"}
    assert marketing["company"] is None  # Lever does not name the company in a posting; it is not guessed
    assert marketing["apply_url"] == "https://jobs.lever.co/fabrikam/5f1c2b3a-1111-4a2b-9c3d-000000000001"
    detail = boards["api"].get(f"/jobs/{found['Account Executive, Mid-Market']['job_id']}").json()
    assert detail["is_remote"] and detail["listing"] == "real"


def test_an_official_career_page_through_the_api(boards):
    crawl(boards, ACADEMY)
    found = jobs(boards, source="generic")
    assert {title: (j["industry"], j["company"]) for title, j in found.items()} == {
        "Mathematics Teacher (Grades 9-12)": ("education", "Riverside Academy"),
        "HR Generalist": ("human_resources", "Riverside Academy"),
        "Data Analyst": ("ai_data", "Riverside Academy")}


def test_a_crawl_may_name_the_job_board_extractor(boards):
    crawl(boards, GREENHOUSE, extractor="greenhouse")
    assert total(boards, source="greenhouse") == 5


def test_robots_txt_can_stop_a_job_board_crawl(boards):
    boards["site"] = site(robots={"https://boards-api.greenhouse.io": "User-agent: *\nDisallow: /\n"})
    response = boards["api"].post("/background-jobs/crawl", json={"seed_url": GREENHOUSE, "max_depth": 1, "max_pages": 5})
    detail = boards["api"].get(f"/background-jobs/{response.json()['background_job_id']}").json()
    assert detail["status"] == "failed" and "robots.txt" in detail["error_message"]
    assert total(boards) == 0 and boards["site"].page_requests() == []


# --- De-duplication ------------------------------------------------------------------------------------


def test_crawling_a_board_again_updates_instead_of_duplicating(boards):
    crawl(boards, GREENHOUSE)
    with SessionLocal() as session:
        first = dict(session.execute(select(Job.apply_url, Job.updated_at)).all())
    crawl(boards, GREENHOUSE)
    with SessionLocal() as session:
        second = dict(session.execute(select(Job.apply_url, Job.updated_at)).all())
    assert set(first) == set(second) and len(second) == 5
    assert all(second[url] > first[url] for url in first)


def test_the_same_posting_twice_in_one_response_is_one_job(boards):
    body = json_fixture("greenhouse_jobs.json").replace("/jobs/4011003", "/jobs/4011001")  # two postings, one URL
    boards["site"] = site(pages={GREENHOUSE: (200, body, JSON)})
    crawl(boards, GREENHOUSE)
    with SessionLocal() as session:
        urls = session.execute(select(Job.apply_url)).scalars().all()
    assert len(urls) == len(set(urls)) == 4


# --- Real and demo jobs side by side ---------------------------------------------------------------------


def test_real_and_demo_listings_are_told_apart(boards):
    crawl(boards, GREENHOUSE)
    crawl(boards, LEVER)
    crawl(boards, MOCK_SEED, max_depth=2)
    demo = jobs(boards, listing="demo")
    real = jobs(boards, listing="real")
    assert len(demo) == 8 and {j["source"] for j in demo.values()} == {"mock_static", "mock_dynamic"}
    assert {j["listing"] for j in demo.values()} == {"demo"}
    assert len(real) == 10 and {j["source"] for j in real.values()} == {"greenhouse", "lever"}
    assert total(boards) == 18 == total(boards, listing="real") + total(boards, listing="demo")
    # The filters combine with the existing ones
    assert set(jobs(boards, industry="healthcare")) == {"Registered Nurse, Occupational Health"}
    assert set(jobs(boards, listing="real", industry="software_it")) == {"Backend Software Engineer"}
    assert total(boards, listing="demo", industry="software_it") >= 1
    assert set(jobs(boards, source="lever", skill="seo")) == {"Growth Marketing Manager"}
    assert set(jobs(boards, listing="real", location="mumbai")) == {"Registered Nurse, Occupational Health",
                                                                    "Corporate Paralegal"}
    assert total(boards, source="fake_python_jobs") == 0


def test_jobs_from_a_demo_site_can_never_be_saved_as_real(boards):
    response = boards["api"].post("/background-jobs/crawl", json={
        "seed_url": MOCK_SEED, "max_depth": 1, "max_pages": 5, "extractor": "generic"})
    assert response.status_code == 422
    assert response.json()["error"]["details"]["errors"][0]["field"] == "body.extractor"
    response = boards["api"].post("/background-jobs/crawl", json={
        "seed_url": GREENHOUSE, "max_depth": 1, "max_pages": 5, "extractor": "greenhouse",
        "allowed_domains": ["boards-api.greenhouse.io", "mock-site"]})
    assert response.status_code == 422
    assert total(boards) == 0


# --- Exports keep the source --------------------------------------------------------------------------------


def test_exports_keep_the_source_listing_and_industry(boards):
    crawl(boards, GREENHOUSE)
    crawl(boards, MOCK_SEED, max_depth=2)
    rows = list(csv.DictReader(io.StringIO(boards["api"].get("/exports/jobs?format=csv").text)))
    assert len(rows) == 13
    nurse = next(r for r in rows if r["title"] == "Registered Nurse, Occupational Health")
    assert (nurse["source"], nurse["listing"], nurse["industry"], nurse["source_url"], nurse["apply_url"]) == (
        "greenhouse", "real", "healthcare", GREENHOUSE, "https://job-boards.greenhouse.io/contosogroup/jobs/4011002")
    assert {r["listing"] for r in rows if r["source"].startswith("mock_")} == {"demo"}

    demo_only = list(csv.DictReader(io.StringIO(boards["api"].get("/exports/jobs?format=csv&listing=demo").text)))
    assert len(demo_only) == 8 and {r["listing"] for r in demo_only} == {"demo"}
    exported = boards["api"].get("/exports/jobs?format=json&listing=real&industry=engineering").json()
    assert [(j["title"], j["source"], j["listing"], j["industry"], j["source_url"]) for j in exported] == [
        ("Mechanical Design Engineer", "greenhouse", "real", "engineering", GREENHOUSE)]


# --- One matching engine for every job -------------------------------------------------------------------------


def test_real_and_demo_jobs_are_matched_by_the_same_engine(boards):
    crawl(boards, GREENHOUSE)
    crawl(boards, MOCK_SEED, max_depth=2)
    nurse = add_candidate(skills=["BLS", "ACLS", "Patient Care", "Electronic Health Records"], years=3, city="Mumbai",
                          title="Staff Nurse")
    developer = add_candidate(skills=["Python", "FastAPI", "PostgreSQL", "Docker", "Django"], years=4, city="Pune")
    response = boards["api"].post("/background-jobs/match")
    assert response.status_code == 202
    assert boards["api"].get(f"/background-jobs/{response.json()['background_job_id']}").json()["status"] == "completed"

    with SessionLocal() as session:
        stored = {(m.candidate_id, m.job_id): m.score for m in session.execute(select(Match)).scalars()}
        jobs_by_title = dict(session.execute(select(Job.title, Job.job_id)).all())
        assert session.execute(select(func.count()).select_from(Job)).scalar_one() == 13
        job_inputs, candidate_inputs = load_inputs(session)
    assert len(stored) == 2 * 13  # every candidate against every job, real and demo alike

    # Every stored score is exactly what the one scoring function gives, whatever the job's source.
    weights = Weights.from_settings(get_settings().match_weights)
    for job in job_inputs:
        for person in candidate_inputs:
            assert stored[(person.candidate_id, job.job_id)] == float(score_pair(job.profile, person.profile, weights).score)

    # Worked by hand: 4 of 4 required (70), nothing nice-to-have listed (15), 3 of 2 years (10), same city (5)
    assert stored[(nurse, jobs_by_title["Registered Nurse, Occupational Health"])] == 100.0
    # 4 of 4 required (70), Kubernetes missing (0 of 15), no minimum stated (10), a remote job (5)
    assert stored[(developer, jobs_by_title["Backend Software Engineer"])] == 85.0
    top = boards["api"].get(f"/candidates/{nurse}/matches").json()["items"][0]
    assert top["title"] == "Registered Nurse, Occupational Health"


def test_unknown_sources_are_never_shown_as_real(boards):
    with SessionLocal() as session:  # e.g. a row from a source whose extractor no longer exists
        session.add(Job(title="Orphan job", apply_url="https://old.example/1", source="retired_board",
                        dedup_key=uuid.uuid4().hex))
        session.commit()
    assert jobs(boards)["Orphan job"]["listing"] == "demo"
    assert total(boards, listing="real") == 0 and total(boards, listing="demo") == 1


def test_reclassify_brings_stored_jobs_up_to_date_and_writes_only_industry(boards, capsys):
    from datetime import UTC, datetime

    from app.services import reclassify

    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    with SessionLocal() as session:  # stored before a rules change: classified "other"
        session.add_all([Job(title="Engineer, automotive", apply_url="https://a.example/1", source="greenhouse",
                             dedup_key="r1", industry="other", updated_at=stamp),
                         Job(title="Barista", apply_url="https://a.example/2", source="greenhouse", dedup_key="r2",
                             industry="other", updated_at=stamp)])
        session.commit()
    assert reclassify.main([]) == 0  # a dry run writes nothing
    assert "Would change the industry of 1 jobs." in capsys.readouterr().out
    with SessionLocal() as session:
        assert session.execute(select(Job.industry).where(Job.dedup_key == "r1")).scalar_one() == "other"
    assert reclassify.main(["--apply"]) == 0
    with SessionLocal() as session:
        rows = {r.dedup_key: (r.industry, r.updated_at) for r in session.execute(select(Job.dedup_key, Job.industry, Job.updated_at))}
    assert rows == {"r1": ("engineering", stamp), "r2": ("other", stamp)}
    assert reclassify.main([]) == 0 and "Would change the industry of 0 jobs." in capsys.readouterr().out
