"""End to end, offline: API -> background job -> Celery task -> crawler -> PostgreSQL (LLD §9.8).

The site is the repository's mock-site/ directory served by httpx.MockTransport under
http://mock-site:8080, and the browser returns the saved rendered snapshot. Celery executes the
real `crawl` task in this process (`Task.apply`), so the API, the task, the crawler and the
database all run exactly as in production, without Redis or the internet.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.crawler import browser, fetcher
from app.db.session import SessionLocal
from app.main import app
from app.models import BackgroundJob, BackgroundJobLog, Job, JobSkill, Skill
from app.services import background_jobs as service
from app.worker import tasks
from app.worker.celery_app import celery_app
from tests.crawl_fakes import FakeRenderer, FakeSite, fixture

MOCK_SITE = Path(__file__).resolve().parents[3] / "mock-site"
ORIGIN = "http://mock-site:8080"
SEED = f"{ORIGIN}/static/index.html"


def mock_site(**overrides) -> FakeSite:
    pages = {f"{ORIGIN}/{p.relative_to(MOCK_SITE).as_posix()}": p.read_text(encoding="utf-8")
             for p in MOCK_SITE.rglob("*.html")}
    pages[f"{ORIGIN}/"] = pages[f"{ORIGIN}/index.html"]
    robots = {ORIGIN: (MOCK_SITE / "robots.txt").read_text(encoding="utf-8")}
    site = FakeSite({**pages, **overrides.pop("pages", {})}, robots={**robots, **overrides.pop("robots", {})}, **overrides)
    return site


@pytest.fixture
def run_with_celery(app_db, fast_crawler, monkeypatch):
    """Publishing runs the task through Celery in this process, against the given fake site."""
    def install(site: FakeSite):
        monkeypatch.setattr(fetcher, "create_client", lambda timeout: site.client())
        monkeypatch.setattr(browser, "BrowserRenderer", lambda **kwargs: FakeRenderer(
            {f"{ORIGIN}/dynamic/index.html": fixture("mock_dynamic_rendered.html")}))
        monkeypatch.setattr(service, "publish_task",
                            lambda name, job_id: celery_app.tasks[name].apply(args=[str(job_id)]).id)
        monkeypatch.setattr(service, "revoke_task", lambda task_id: None)
        return TestClient(app)
    return install


def job_row(job_id) -> BackgroundJob:
    with SessionLocal() as session:
        return session.get(BackgroundJob, job_id)


def log_messages(job_id) -> list[str]:
    with SessionLocal() as session:
        return list(session.execute(select(BackgroundJobLog.message).where(BackgroundJobLog.background_job_id == job_id)
                                    .order_by(BackgroundJobLog.log_id)).scalars())


def test_crawl_through_the_api_saves_jobs_progress_and_logs(run_with_celery):
    site = mock_site()
    api = run_with_celery(site)
    response = api.post("/background-jobs/crawl", json={"seed_url": SEED, "max_depth": 2, "max_pages": 30})
    assert response.status_code == 202
    job_id = response.json()["background_job_id"]

    job = job_row(job_id)
    assert job.status == "completed" and job.started_at and job.finished_at and job.heartbeat_at
    assert job.celery_task_id  # set from Celery's task id
    # 11 pages: the seed, 7 at depth 1 (incl. robots-disallowed /private/ and a 404), 2 at depth 2
    assert (job.progress_current, job.progress_total, job.items_succeeded, job.items_failed) == (11, 11, 9, 1)
    detail = api.get(f"/background-jobs/{job_id}").json()
    assert detail["progress"] == {"current": 11, "total": 11, "percent": 100}

    with SessionLocal() as session:
        jobs = session.execute(select(Job).order_by(Job.title)).scalars().all()
        assert len(jobs) == 8  # 5 static (listing + detail merged) + 3 rendered by JavaScript
        assert {j.source for j in jobs} == {"mock_static", "mock_dynamic"}
        assert all(j.background_job_id == job.background_job_id for j in jobs)
        backend = next(j for j in jobs if j.title == "Backend Python Developer")
        levels = dict(session.execute(select(Skill.canonical_name, JobSkill.requirement_level).join(Skill)
                                      .where(JobSkill.job_id == backend.job_id)).all())
        assert levels == {"Python": "required", "FastAPI": "required", "Django": "required", "PostgreSQL": "required",
                          "Pytest": "required", "Docker": "nice_to_have", "Redis": "nice_to_have", "Kubernetes": "nice_to_have"}
        assert session.execute(select(func.count()).select_from(Skill)).scalar_one() >= 20

    messages = log_messages(job_id)
    assert messages[0].startswith(f"Crawl started: {SEED}")
    assert any(m.startswith("Skipped http://mock-site:8080/private/internal.html: disallowed by robots.txt") for m in messages)
    assert any(m == "Failed http://mock-site:8080/static/archived-jobs.html: HTTP 404" for m in messages)
    assert any(m.startswith("Rendering http://mock-site:8080/dynamic/index.html in a headless browser") for m in messages)
    assert any(m.startswith("Crawl finished: 11 pages processed (9 succeeded, 1 failed, 1 skipped)") for m in messages)
    assert f"{ORIGIN}/static/archived-jobs.html" in site.requests and f"{ORIGIN}/private/internal.html" not in site.requests

    logs = api.get(f"/background-jobs/{job_id}/logs?level=WARNING").json()["items"]
    assert [i["level"] for i in logs] == ["ERROR"]  # only the 404


def test_crawling_twice_updates_instead_of_duplicating(run_with_celery):
    api = run_with_celery(mock_site())
    for _ in range(2):
        assert api.post("/background-jobs/crawl", json={"seed_url": SEED, "max_depth": 2, "max_pages": 30}).status_code == 202
    with SessionLocal() as session:
        assert session.execute(select(func.count()).select_from(Job)).scalar_one() == 8


def test_cancelling_a_running_crawl(run_with_celery):
    def cancel_on_detail_page(url):
        if url.endswith("/static/jobs/frontend-engineer-react.html"):
            with SessionLocal() as session:
                running = session.execute(select(BackgroundJob.background_job_id)
                                          .where(BackgroundJob.status == "running")).scalar_one()
                assert service.cancel_job(session, running)[0] == 202

    api = run_with_celery(mock_site(on_request=cancel_on_detail_page))
    job_id = api.post("/background-jobs/crawl", json={"seed_url": SEED, "max_depth": 2, "max_pages": 30}).json()["background_job_id"]

    job = job_row(job_id)
    assert job.status == "cancelled" and job.cancel_requested and job.finished_at
    assert job.progress_current < 11  # stopped early
    messages = log_messages(job_id)
    assert f"Cancelled by user after {job.progress_current} items." in messages
    with SessionLocal() as session:
        assert session.execute(select(func.count()).select_from(Job)).scalar_one() >= 3  # saved jobs are kept


def test_cancelling_a_queued_crawl_means_the_task_does_nothing(app_db, fast_crawler, published, monkeypatch):
    site = mock_site()
    monkeypatch.setattr(fetcher, "create_client", lambda timeout: site.client())
    api = TestClient(app)
    job_id = api.post("/background-jobs/crawl", json={"seed_url": SEED, "max_depth": 1, "max_pages": 5}).json()["background_job_id"]
    assert api.post(f"/background-jobs/{job_id}/cancel").json() == {"status": "cancelled"}

    assert celery_app.tasks["crawl"].apply(args=[job_id]).get() == "not-claimed"  # the message arrives late
    assert job_row(job_id).status == "cancelled" and site.requests == []


def test_seed_disallowed_by_robots_txt_fails_the_job(run_with_celery):
    api = run_with_celery(mock_site(robots={ORIGIN: "User-agent: *\nDisallow: /static/\n"}))
    job_id = api.post("/background-jobs/crawl", json={"seed_url": SEED, "max_depth": 1, "max_pages": 5}).json()["background_job_id"]
    job = job_row(job_id)
    assert (job.status, job.error_message) == ("failed", f"Seed URL {SEED} is disallowed by robots.txt.")
    assert log_messages(job_id)[-1] == job.error_message


def test_every_page_failing_fails_the_job(run_with_celery):
    api = run_with_celery(mock_site(pages={SEED: (500, "down")}))
    job_id = api.post("/background-jobs/crawl", json={"seed_url": SEED, "max_depth": 1, "max_pages": 5}).json()["background_job_id"]
    job = job_row(job_id)
    assert (job.status, job.error_message, job.items_failed) == ("failed", "All 1 pages failed.", 1)


def test_job_ended_elsewhere_is_not_overwritten(run_with_celery):
    """If the stale-job check fails a crawl while it still runs, the worker stops and leaves it failed."""
    def fail_it(url):
        if url.endswith("/static/page-2.html"):
            with SessionLocal() as session:
                session.execute(BackgroundJob.__table__.update().where(BackgroundJob.status == "running")
                                .values(status="failed", error_message="Worker stopped unexpectedly."))
                session.commit()

    api = run_with_celery(mock_site(on_request=fail_it))
    job_id = api.post("/background-jobs/crawl", json={"seed_url": SEED, "max_depth": 2, "max_pages": 30}).json()["background_job_id"]
    job = job_row(job_id)
    assert (job.status, job.error_message) == ("failed", "Worker stopped unexpectedly.")
    assert tasks.run_crawl_job(job.background_job_id) == "not-claimed"
