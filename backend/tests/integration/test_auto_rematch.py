"""Automatic re-matching after a crawl, against PostgreSQL (LLD §7.1).

Change detection is tested on `save_records` directly: each value matching reads, and the
columns it never reads. The trigger is tested end to end: the real `crawl` task crawls a fake job
board (httpx.MockTransport, JSON-LD postings), and publishing a `match` task only records it, so
the queued run can be inspected and then run on purpose. The people are invented.
"""

import json
import threading
import uuid
from datetime import UTC, datetime

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from fastapi.testclient import TestClient
from sqlalchemy import func, insert, select, text, update

from app.config import get_settings
from app.crawler import fetcher
from app.crawler.pipeline import build_record, save_records
from app.db.session import SessionLocal
from app.extractors.base import RawJob
from app.main import app
from app.models import BackgroundJob, BackgroundJobLog, Job, JobSkill, Match
from app.services import background_jobs as service
from app.worker import tasks
from app.worker.celery_app import celery_app
from tests.crawl_fakes import FakeSite, html_page
from tests.integration.test_match_flow import DEFAULT_WEIGHTS, Gate, add_candidate, run_in_thread, run_task, wait_for

CUSTOM = {"required": 60, "nice": 20, "experience": 10, "location": 10}

# --- Change detection (save_records) -----------------------------------------------------------

NOW = datetime(2026, 11, 22, tzinfo=UTC)
LISTED = {"title": "Backend Developer", "company": "Acme", "location": "Pune, India",
          "description": "Build APIs in Python.", "apply_url": "https://jobs.example.com/1",
          "required_skills": ["Python", "FastAPI"], "nice_to_have_skills": ["Docker"], "min_experience_years": 2}


def save(session, **changes):
    built = build_record(RawJob(**{**LISTED, **changes}), page_url="https://jobs.example.com/board", source="test",
                         fetched_at=NOW)
    return save_records(session, [built], None)


def test_a_new_job_counts_as_changed(session):
    result = save(session)
    assert result.inserted == 1 and len(result.match_inputs_changed) == 1


def test_saving_an_unchanged_job_again_is_an_update_but_not_a_change(session):
    save(session)
    again = save(session)
    assert (again.inserted, again.updated, again.match_inputs_changed) == (0, 1, [])


@pytest.mark.parametrize("change", [
    {"required_skills": ["Python", "Django"]},
    {"nice_to_have_skills": ["Kubernetes"]},
    {"required_skills": ["Python", "FastAPI", "Docker"], "nice_to_have_skills": []},  # Docker is now required
    {"min_experience_years": 3},
    {"location": "Mumbai, India"},
    {"is_remote": True},
    {"description": "Build and run APIs in Python."},
], ids=["required-skills", "nice-to-have-skills", "skill-level", "experience", "location", "remote", "description"])
def test_a_change_to_what_matching_reads_counts(session, change):
    (job_id,) = save(session).match_inputs_changed
    result = save(session, **change)
    assert (result.updated, result.match_inputs_changed) == (1, [job_id])


@pytest.mark.parametrize("change", [
    {"title": "Senior Backend Developer"},
    {"company": "Acme Analytics"},
    {"salary_text": "₹10,00,000 per year"},
    {"posted_date": "2026-11-01"},
    {"job_type": "Full-time"},
    # A listing card with less information: empty values never erase stored ones (LLD §3.6)
    {"description": None, "required_skills": None, "nice_to_have_skills": None, "min_experience_years": None,
     "location": None},
], ids=["title", "company", "salary", "posted-date", "job-type", "less-information"])
def test_a_change_matching_never_reads_does_not_count(session, change):
    save(session)
    result = save(session, **change)
    assert (result.updated, result.match_inputs_changed) == (1, [])


# --- The trigger, end to end -------------------------------------------------------------------

# A real-source board (not the demo mock-site host: the crawler takes jobs there only through its demo extractors).
ORIGIN = "http://careers-board:8080"
SEED = f"{ORIGIN}/board/index.html"
PAGE_2 = f"{ORIGIN}/board/page2.html"


def posting(n: int = 1, **changes) -> dict:
    return {"@context": "https://schema.org", "@type": "JobPosting", "title": f"Backend Developer {n}",
            "hiringOrganization": {"name": "Acme"}, "url": f"{ORIGIN}/board/jobs/{n}",
            "jobLocation": {"address": {"addressLocality": "Pune", "addressCountry": "India"}},
            "description": "Build APIs in Python and FastAPI.", "skills": "Python, FastAPI",
            "experienceRequirements": {"monthsOfExperience": 24}, **changes}


def board(*postings: dict, links: list[str] = (), on_request=None) -> FakeSite:
    """A one-page job board with JSON-LD postings (and optional links to empty pages)."""
    scripts = "".join(f'<script type="application/ld+json">{json.dumps(p)}</script>' for p in postings)
    pages = {SEED: html_page(scripts, links=list(links), title="Job board")}
    pages.update({link: html_page("No jobs here.") for link in links})
    return FakeSite(pages, on_request=on_request)


@pytest.fixture
def crawl_env(app_db, fast_crawler, monkeypatch):
    """A crawl task runs at once against state["site"]; a published match task is only recorded."""
    state = {"site": board(posting()), "published": [], "broker_down": False}
    monkeypatch.setattr(fast_crawler, "crawler_private_host_allowlist", ["careers-board"])  # served by the fake site
    monkeypatch.setattr(fetcher, "create_client", lambda timeout: state["site"].client())

    def publish(name, job_id):
        if name != "match":
            return celery_app.tasks[name].apply(args=[str(job_id)]).id
        if state["broker_down"]:
            raise ConnectionError("simulated: Redis is down")
        state["published"].append(job_id)
        return f"match-{len(state['published'])}"

    monkeypatch.setattr(service, "publish_task", publish)
    monkeypatch.setattr(service, "revoke_task", lambda task_id: None)
    state["api"] = TestClient(app)
    return state


def crawl(env, site: FakeSite | None = None) -> uuid.UUID:
    """Run one crawl of the board to its end (the automatic request included)."""
    if site is not None:
        env["site"] = site
    response = env["api"].post("/background-jobs/crawl", json={"seed_url": SEED, "max_depth": 1, "max_pages": 5,
                                                                 "extractor": "generic"})
    assert response.status_code == 202, response.text
    return uuid.UUID(response.json()["background_job_id"])


def row(job_id) -> BackgroundJob:
    with SessionLocal() as session:
        return session.get(BackgroundJob, job_id)


def match_runs() -> list[BackgroundJob]:
    """All match runs, oldest first."""
    with SessionLocal() as session:
        return list(session.execute(select(BackgroundJob).where(BackgroundJob.type == "match")
                                    .order_by(BackgroundJob.created_at, BackgroundJob.background_job_id)).scalars())


def log_of(job_id) -> list[tuple[str, str]]:
    with SessionLocal() as session:
        return [(level, message) for level, message in session.execute(
            select(BackgroundJobLog.level, BackgroundJobLog.message)
            .where(BackgroundJobLog.background_job_id == job_id).order_by(BackgroundJobLog.log_id))]


def messages(job_id) -> list[str]:
    return [message for _, message in log_of(job_id)]


def auto_lines(crawl_id) -> list[str]:
    return [m for m in messages(crawl_id) if "saved by this crawl" in m]


def short(job_id) -> str:
    return f"#{str(job_id)[:8]}"


def run_queued() -> None:
    for run in match_runs():
        if run.status == "queued":
            run_task(run.background_job_id)


def scores() -> list[float]:
    with SessionLocal() as session:
        return sorted(session.execute(select(Match.score)).scalars())


SUMMARY_1 = "1 job saved by this crawl is new or changed in what matching reads"


def test_a_crawl_that_saves_a_new_job_queues_a_match_run(crawl_env):
    add_candidate(skills=["Python", "FastAPI"], years=3, city="Pune")
    crawl_id = crawl(crawl_env)
    assert row(crawl_id).status == "completed"

    (run,) = match_runs()
    assert run.status == "queued" and crawl_env["published"] == [run.background_job_id]
    # The run records the active weights and the crawl it was started after
    assert run.params == {"weights": DEFAULT_WEIGHTS, "after_crawl": str(crawl_id)}
    assert auto_lines(crawl_id) == [f"{SUMMARY_1}: match run {short(run.background_job_id)} was queued "
                                    "automatically with the active weights (70 / 15 / 10 / 5)."]
    detail = crawl_env["api"].get(f"/background-jobs/{run.background_job_id}").json()
    assert detail["params"] == {"weights": DEFAULT_WEIGHTS, "after_crawl": str(crawl_id)}

    # It runs like any match run, and the new job is matched
    assert run_task(run.background_job_id) == "completed"
    assert messages(run.background_job_id)[0] == (f"Started automatically after crawl {short(crawl_id)} "
                                                 "saved new or changed jobs.")
    assert scores() == [100.0]  # 2 of 2 required skills, none nice-to-have, 3 of 2 years, same city


@pytest.mark.parametrize("change", [
    {"skills": "Python, Django"},
    {"experienceRequirements": {"monthsOfExperience": 60}},
    {"jobLocation": {"address": {"addressLocality": "Mumbai", "addressCountry": "India"}}},
    {"jobLocationType": "TELECOMMUTE"},
], ids=["skills", "experience", "location", "remote"])
def test_a_recrawl_that_changes_what_matching_reads_queues_a_match_run(crawl_env, change):
    add_candidate(skills=["Python"])
    crawl(crawl_env)
    run_queued()
    second = crawl(crawl_env, board(posting(**change)))

    first_run, second_run = match_runs()
    assert first_run.status == "completed" and second_run.status == "queued"
    assert second_run.params["after_crawl"] == str(second)
    assert auto_lines(second) == [f"{SUMMARY_1}: match run {short(second_run.background_job_id)} was queued "
                                  "automatically with the active weights (70 / 15 / 10 / 5)."]


def job_state() -> tuple:
    with SessionLocal() as session:
        (job,) = session.execute(select(Job)).scalars().all()
        links = {(skill_id, level) for skill_id, level in session.execute(select(JobSkill.skill_id, JobSkill.requirement_level))}
        return job, links


def test_an_unchanged_recrawl_queues_nothing(crawl_env):
    add_candidate(skills=["Python"])
    crawl(crawl_env)
    run_queued()
    before, links_before = job_state()

    again = crawl(crawl_env)
    assert row(again).status == "completed"
    assert len(match_runs()) == 1 and auto_lines(again) == []
    # The job was saved again (its update time moved); nothing matching reads changed
    after, links_after = job_state()
    assert after.updated_at > before.updated_at and after.background_job_id == again
    assert links_after == links_before
    assert any("1 saved (0 new, 1 updated)" in m for m in messages(again))


def test_a_change_matching_never_reads_queues_nothing(crawl_env):
    add_candidate(skills=["Python"])
    crawl(crawl_env)
    run_queued()
    again = crawl(crawl_env, board(posting(title="Senior Backend Developer", hiringOrganization={"name": "Acme Labs"},
                                           baseSalary={"currency": "INR", "value": 1200000})))
    job, _ = job_state()
    assert (job.title, job.company, job.salary_min) == ("Senior Backend Developer", "Acme Labs", 1200000)
    assert len(match_runs()) == 1 and auto_lines(again) == []


def test_a_description_only_change_queues_a_match_run(crawl_env):
    add_candidate(skills=["Python"])
    crawl(crawl_env)
    run_queued()
    before, links_before = job_state()

    second = crawl(crawl_env, board(posting(description="Build APIs in Python and FastAPI. A small team in Pune.")))
    after, links_after = job_state()
    # Only the description changed; it is the job's text for the TF-IDF tie-breaker
    assert after.description != before.description and links_after == links_before
    assert (after.min_experience_years, after.location, after.is_remote) == (
        before.min_experience_years, before.location, before.is_remote)
    assert match_runs()[-1].params["after_crawl"] == str(second) and len(match_runs()) == 2


@pytest.mark.parametrize("ending", ["time-limit", "stale-job-check"])
def test_a_failed_crawl_that_saved_jobs_queues_a_match_run(crawl_env, monkeypatch, ending):
    add_candidate(skills=["Python"])
    real = tasks.JobRun.page_done

    def page_done(run, stats):  # after the first page, whose job is already saved
        if ending == "time-limit":
            raise SoftTimeLimitExceeded()
        with SessionLocal() as session:  # the stale-job check fails the crawl while it runs
            session.execute(update(BackgroundJob).where(BackgroundJob.background_job_id == run.job_id)
                            .values(status="failed", finished_at=func.now(), error_message="Worker stopped unexpectedly."))
            session.commit()
        return real(run, stats)

    monkeypatch.setattr(tasks.JobRun, "page_done", page_done)
    crawl_id = crawl(crawl_env)

    crawl_row = row(crawl_id)
    assert crawl_row.status == "failed"
    assert crawl_row.error_message == ("Time limit exceeded." if ending == "time-limit" else "Worker stopped unexpectedly.")
    (run,) = match_runs()
    assert run.status == "queued" and run.params["after_crawl"] == str(crawl_id)
    assert len(auto_lines(crawl_id)) == 1


def test_a_failed_crawl_that_saved_nothing_queues_nothing(crawl_env):
    add_candidate(skills=["Python"])
    crawl_id = crawl(crawl_env, FakeSite({SEED: (500, "down")}))
    assert row(crawl_id).status == "failed"
    assert match_runs() == [] and auto_lines(crawl_id) == []


def test_a_cancelled_crawl_queues_nothing(crawl_env):
    add_candidate(skills=["Python"])

    def cancel_on_page_2(url):
        if url == PAGE_2:
            with SessionLocal() as session:
                running = session.execute(select(BackgroundJob.background_job_id)
                                          .where(BackgroundJob.status == "running")).scalar_one()
                assert service.cancel_job(session, running)[0] == 202

    crawl_id = crawl(crawl_env, board(posting(), links=[PAGE_2], on_request=cancel_on_page_2))
    assert row(crawl_id).status == "cancelled"
    assert match_runs() == [] and crawl_env["published"] == []
    assert auto_lines(crawl_id) == [f"{SUMMARY_1}. The crawl was cancelled, so no match run was queued; "
                                    "recompute matches to include them."]
    job, _ = job_state()  # the job it saved is kept
    assert job.background_job_id == crawl_id


def test_no_candidates_means_no_match_run(crawl_env):
    crawl_id = crawl(crawl_env)
    assert row(crawl_id).status == "completed"
    assert match_runs() == []
    assert auto_lines(crawl_id) == [f"{SUMMARY_1}, but there are no candidates yet, so no match run was queued."]


def test_auto_rematch_false_turns_it_off(crawl_env, monkeypatch):
    add_candidate(skills=["Python"])
    monkeypatch.setattr(get_settings(), "auto_rematch", False)
    crawl_id = crawl(crawl_env)
    assert row(crawl_id).status == "completed" and match_runs() == []
    assert auto_lines(crawl_id) == [f"{SUMMARY_1}. AUTO_REMATCH is off, so no match run was queued; "
                                    "recompute matches to include them."]
    assert crawl_env["api"].post("/background-jobs/match").status_code == 202  # recomputing by hand still works


def test_a_queued_match_run_is_not_duplicated_and_includes_the_new_jobs(crawl_env):
    add_candidate(skills=["Python"])
    first = crawl(crawl_env)
    second = crawl(crawl_env, board(posting(), posting(2)))  # a new job while the first run is still queued

    (run,) = match_runs()
    assert run.params["after_crawl"] == str(first)
    assert auto_lines(second) == [f"{SUMMARY_1}; match run {short(run.background_job_id)} is already queued and "
                                  "will include them, so no other run was queued."]
    assert run_task(run.background_job_id) == "completed"
    assert len(scores()) == 2  # it loads the jobs when it starts: the second crawl's job is matched too


def test_the_same_crawl_never_queues_a_second_run(crawl_env):
    add_candidate(skills=["Python"])
    crawl_id = crawl(crawl_env)
    (run,) = match_runs()
    assert run_task(run.background_job_id) == "completed"  # no longer queued
    with SessionLocal() as session:
        assert service.request_auto_match(session, crawl_id) == ("already_requested", run.background_job_id)
    assert len(match_runs()) == 1 and len(crawl_env["published"]) == 1


def advisory_lock_waiters() -> int:
    with SessionLocal() as session:
        return session.execute(text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted")).scalar_one()


def test_an_automatic_request_waits_for_a_manual_one_and_does_not_duplicate_it(crawl_env, app_db):
    add_candidate(skills=["Python"])
    # A manual request half way: it holds the lock and has inserted its queued run, not yet committed
    holder = app_db.connect()
    transaction = holder.begin()
    holder.execute(select(func.pg_advisory_xact_lock(service.MATCH_QUEUE_LOCK)))
    manual = uuid.uuid4()
    holder.execute(insert(BackgroundJob).values(background_job_id=manual, type="match", status="queued",
                                                params={"weights": CUSTOM}))
    results = {}

    def automatic():
        with SessionLocal() as session:
            results["auto"] = service.request_auto_match(session, uuid.uuid4())

    thread = threading.Thread(target=automatic)
    thread.start()
    try:
        wait_for(lambda: advisory_lock_waiters() == 1)  # the automatic request waits for the lock
        assert "auto" not in results
    finally:
        transaction.commit()
        holder.close()
    thread.join(10)
    assert results["auto"] == ("already_queued", manual)
    assert [r.background_job_id for r in match_runs()] == [manual] and crawl_env["published"] == []


def test_automatic_requests_at_the_same_time_queue_one_run(crawl_env):
    add_candidate(skills=["Python"])
    for _ in range(5):
        start = threading.Barrier(3)
        results: list = []

        def automatic():
            start.wait()
            with SessionLocal() as session:
                results.append(service.request_auto_match(session, uuid.uuid4()))

        threads = [threading.Thread(target=automatic) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        assert sorted(outcome for outcome, _ in results) == ["already_queued", "already_queued", "queued"]
        assert len({run_id for _, run_id in results}) == 1  # the other two name the run that was queued
        queued = [r for r in match_runs() if r.status == "queued"]
        assert len(queued) == 1
        with SessionLocal() as session:  # clear it for the next round
            service.cancel_job(session, queued[0].background_job_id)


def test_a_manual_recompute_is_still_queued_after_an_automatic_run(crawl_env):
    add_candidate(skills=["Python"])
    crawl(crawl_env)
    response = crawl_env["api"].post("/background-jobs/match", json={"weights": CUSTOM})
    assert response.status_code == 202
    auto, manual = match_runs()
    assert auto.params["after_crawl"] and manual.params == {"weights": CUSTOM}
    assert auto.status == manual.status == "queued"


def test_automatic_runs_use_the_active_custom_weights(crawl_env):
    add_candidate(skills=["Python", "FastAPI"], years=1, city="Mumbai")
    crawl(crawl_env)
    assert crawl_env["api"].post("/background-jobs/match", json={"weights": CUSTOM}).status_code == 202
    run_queued()  # the automatic run, then the manual one with the custom weights: both complete
    assert [r.status for r in match_runs()] == ["completed", "completed"]

    second = crawl(crawl_env, board(posting(), posting(2)))
    run = match_runs()[-1]
    assert run.params == {"weights": CUSTOM, "after_crawl": str(second)}
    assert auto_lines(second) == [f"{SUMMARY_1}: match run {short(run.background_job_id)} was queued "
                                  "automatically with the active weights (60 / 20 / 10 / 10)."]
    assert run_task(run.background_job_id) == "completed"
    # 60 (2 of 2 required) + 20 (none nice-to-have) + 5 (1 of 2 years) + 0 (other city); 90 with the defaults
    assert scores() == [85.0, 85.0]


def test_a_broker_failure_does_not_change_the_crawl(crawl_env):
    add_candidate(skills=["Python"])
    crawl_env["broker_down"] = True
    crawl_id = crawl(crawl_env)

    crawl_row = row(crawl_id)
    assert (crawl_row.status, crawl_row.error_message) == ("completed", None)
    (run,) = match_runs()
    assert (run.status, run.error_message) == ("failed", "The job could not be queued: the message broker is unavailable.")
    assert run.params["after_crawl"] == str(crawl_id)
    assert log_of(crawl_id)[-1] == ("WARNING", f"{SUMMARY_1}, but the automatic match run could not be queued: the "
                                               "message broker is unavailable. Recompute matches when it is back.")
    assert not [m for level, m in log_of(crawl_id) if level == "ERROR"]

    crawl_env["broker_down"] = False  # the next crawl with changes tries again: a failed run is not queued
    second = crawl(crawl_env, board(posting(), posting(2)))
    assert [r.status for r in match_runs()] == ["failed", "queued"]
    assert match_runs()[-1].params["after_crawl"] == str(second)


def test_a_running_match_run_does_not_stop_a_new_one(crawl_env, monkeypatch):
    add_candidate(skills=["Python"])
    crawl(crawl_env)
    (first,) = match_runs()
    gate = Gate(monkeypatch)
    gate.hold(first.background_job_id)
    results: dict = {}
    thread = run_in_thread(first.background_job_id, results)
    try:
        assert gate.reached[first.background_job_id].wait(20)  # running: it loaded the jobs before the next crawl
        second = crawl(crawl_env, board(posting(), posting(2)))
    finally:
        gate.go[first.background_job_id].set()
        thread.join(30)
    assert results[first.background_job_id] == "completed"
    newer = match_runs()[-1]
    assert newer.params["after_crawl"] == str(second) and newer.status == "queued"
    assert run_task(newer.background_job_id) == "completed"
    assert len(scores()) == 2


def test_an_automatic_run_never_overwrites_newer_results(crawl_env, monkeypatch):
    add_candidate(skills=["Python", "FastAPI"], years=1, city="Mumbai")
    crawl(crawl_env)
    (auto,) = match_runs()
    gate = Gate(monkeypatch)
    gate.hold(auto.background_job_id)
    results: dict = {}
    thread = run_in_thread(auto.background_job_id, results)
    try:
        assert gate.reached[auto.background_job_id].wait(20)  # scored, waiting just before saving
        response = crawl_env["api"].post("/background-jobs/match", json={"weights": CUSTOM})
        manual = uuid.UUID(response.json()["background_job_id"])
        assert run_task(manual) == "completed"  # started later, saved first
    finally:
        gate.go[auto.background_job_id].set()
        thread.join(30)

    assert results[auto.background_job_id] == "cancelled"
    assert row(auto.background_job_id).error_message == (
        f"Superseded: a newer match run ({short(manual)}) saved its results first; these results were not saved.")
    assert scores() == [85.0]  # the manual run's results (custom weights) stay; the defaults would give 90
