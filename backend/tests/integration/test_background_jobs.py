"""Background jobs against PostgreSQL: API, lifecycle rules, cancellation, progress, logs,
stale-job checks and worker failure handling (LLD Part 5, §9.5, §9.8)."""

import uuid

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.db.session import SessionLocal, session_scope
from app.main import app
from app.models import BackgroundJob, BackgroundJobLog
from app.services import background_jobs as service
from app.services.redaction import INTERNAL_HOST as INTERNAL
from app.worker import progress, tasks

CRAWL = {"seed_url": "https://jobs.example.com/", "max_depth": 2, "max_pages": 50}


@pytest.fixture
def api(app_db):
    return TestClient(app)


def make_job(status="queued", job_type="crawl", **values) -> uuid.UUID:
    with session_scope() as session:
        job = BackgroundJob(type=job_type, status=status, params={"seed_url": "https://jobs.example.com/"}, **values)
        session.add(job)
        session.flush()
        return job.background_job_id


def load(job_id) -> BackgroundJob:
    with SessionLocal() as session:
        return session.get(BackgroundJob, job_id)


def set_times(job_id, **ages_in_seconds):
    """Move timestamps into the past, e.g. set_times(id, created_at=660)."""
    with session_scope() as session:
        for column, seconds in ages_in_seconds.items():
            session.execute(text(f"UPDATE background_jobs SET {column} = now() - make_interval(secs => :s) "
                                 "WHERE background_job_id = :id"), {"s": seconds, "id": job_id})


def logs_of(job_id) -> list[tuple[str, str]]:
    with SessionLocal() as session:
        rows = session.execute(select(BackgroundJobLog).where(BackgroundJobLog.background_job_id == job_id)
                               .order_by(BackgroundJobLog.log_id)).scalars()
        return [(r.level, r.message) for r in rows]


# --- Create and read ----------------------------------------------------------------------------


def test_create_crawl_job(api, published):
    response = api.post("/background-jobs/crawl", json={**CRAWL, "seed_url": "HTTPS://Jobs.Example.com/?utm_source=x"})
    assert response.status_code == 202
    body = response.json()
    assert set(body) == {"background_job_id", "type", "status", "progress", "created_at"}
    assert (body["type"], body["status"], body["progress"]) == ("crawl", "queued", {"current": 0, "total": 50, "percent": 0})

    job = load(body["background_job_id"])
    assert job.params == {"seed_url": "https://jobs.example.com/", "max_depth": 2, "max_pages": 50,
                          "allowed_domains": ["jobs.example.com"], "extractor": None}
    assert job.celery_task_id == "task-1"
    assert published == [("crawl", job.background_job_id)]  # the message carries only the ID (ADR-004)


def test_broker_down_fails_the_job_and_returns_503(api, monkeypatch):
    def broken(task_name, job_id):
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(service, "publish_task", broken)
    response = api.post("/background-jobs/crawl", json=CRAWL)
    assert response.status_code == 503 and response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    with SessionLocal() as session:
        job = session.execute(select(BackgroundJob)).scalar_one()
    assert job.status == "failed" and "could not be queued" in job.error_message


def test_list_filter_and_paginate(api):
    ids = [make_job("completed"), make_job("running", progress_current=18, progress_total=50,
                                           items_succeeded=17, items_failed=1), make_job("queued")]
    response = api.get("/background-jobs?page_size=2")
    body = response.json()
    assert response.status_code == 200 and (body["total"], body["page"], body["page_size"]) == (3, 1, 2)
    assert [i["background_job_id"] for i in body["items"]] == [str(ids[2]), str(ids[1])]  # newest first
    running = body["items"][1]
    assert running["progress"] == {"current": 18, "total": 50, "percent": 36}
    assert (running["items_succeeded"], running["items_failed"], running["finished_at"]) == (17, 1, None)
    assert api.get("/background-jobs?page=2&page_size=2").json()["items"][0]["background_job_id"] == str(ids[0])
    assert [i["status"] for i in api.get("/background-jobs?status=running").json()["items"]] == ["running"]
    assert api.get("/background-jobs?type=resume").json()["total"] == 0


def test_get_one_job(api):
    job_id = make_job("failed", error_message="All 3 pages failed.")
    body = api.get(f"/background-jobs/{job_id}").json()
    assert body["params"] == {"seed_url": "https://jobs.example.com/"}
    assert body["error_message"] == "All 3 pages failed." and body["status"] == "failed"
    missing = api.get(f"/background-jobs/{uuid.uuid4()}")
    assert missing.status_code == 404 and missing.json() == {"error": {"code": "NOT_FOUND", "message": "Background job not found."}}


# --- Lifecycle rules (conditional updates) ------------------------------------------------------


def test_valid_transitions(app_db):
    job_id = make_job("queued")
    with session_scope() as s:
        assert progress.claim(s, job_id)
    job = load(job_id)
    assert job.status == "running" and job.started_at and job.heartbeat_at
    with session_scope() as s:
        assert progress.finish(s, job_id, "completed", progress_total=7)
    job = load(job_id)
    assert (job.status, job.progress_total) == ("completed", 7) and job.finished_at


@pytest.mark.parametrize("status", ["running", "completed", "failed", "cancelled"])
def test_only_a_queued_job_can_be_claimed(app_db, status):
    job_id = make_job(status)
    with session_scope() as s:
        assert not progress.claim(s, job_id)
    assert load(job_id).status == status


@pytest.mark.parametrize("final", ["completed", "failed", "cancelled"])
def test_final_states_are_never_overwritten(app_db, final):
    job_id = make_job(final, error_message=None)
    for status in ("completed", "failed", "cancelled"):
        with session_scope() as s:
            assert not progress.finish(s, job_id, status, error_message="late failure")
    job = load(job_id)
    assert job.status == final and job.error_message is None


def test_a_queued_job_cannot_jump_to_completed(app_db):
    job_id = make_job("queued")
    with session_scope() as s:
        assert not progress.finish(s, job_id, "completed")
    assert load(job_id).status == "queued"


def test_running_is_not_a_final_status(app_db):
    with pytest.raises(ValueError):
        with session_scope() as s:
            progress.finish(s, make_job("running"), "running")


def test_progress_counters_and_heartbeat(app_db):
    job_id = make_job("running", progress_total=50)
    set_times(job_id, heartbeat_at=120)
    before = load(job_id).heartbeat_at
    with session_scope() as s:
        cancel = progress.record_progress(s, job_id, current=4, total=50, succeeded=3, failed=1)
    job = load(job_id)
    assert cancel is False
    assert (job.progress_current, job.items_succeeded, job.items_failed) == (4, 3, 1) and job.heartbeat_at > before
    with session_scope() as s:
        assert progress.record_progress(s, make_job("completed"), current=1, total=1, succeeded=1, failed=0) is None


# --- Cancellation (LLD §5.7) ------------------------------------------------------------------------


def test_cancel_a_queued_job(api, published):
    job_id = make_job("queued", celery_task_id="task-9")
    response = api.post(f"/background-jobs/{job_id}/cancel")
    assert (response.status_code, response.json()) == (200, {"status": "cancelled"})
    assert load(job_id).status == "cancelled" and ("revoke", "task-9") in published
    with session_scope() as s:  # if the message still arrives, the claim fails
        assert not progress.claim(s, job_id)


def test_cancel_a_running_job(api):
    job_id = make_job("running")
    response = api.post(f"/background-jobs/{job_id}/cancel")
    assert (response.status_code, response.json()) == (202, {"status": "running", "cancel_requested": True})
    job = load(job_id)
    assert job.status == "running" and job.cancel_requested
    with session_scope() as s:  # the worker sees the flag after its next item
        assert progress.record_progress(s, job_id, current=1, total=5, succeeded=1, failed=0) is True


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
def test_cancel_a_finished_job_is_a_conflict(api, status):
    response = api.post(f"/background-jobs/{make_job(status)}/cancel")
    assert response.status_code == 409
    assert response.json()["error"] == {"code": "CONFLICT", "message": f"The background job is already {status}."}


def test_cancel_unknown_job(api):
    assert api.post(f"/background-jobs/{uuid.uuid4()}/cancel").status_code == 404


# --- Logs --------------------------------------------------------------------------------------------


def test_job_details_and_logs_are_redacted_but_stored_unchanged(api):
    """GET /background-jobs/{id} and /logs never show credentials, internal hosts, IP addresses, paths, stack
    traces, personal data or storage names; progress stays readable; the stored rows are not changed."""
    raw_params = {"seed_url": "https://admin:hunter2@mock-site:8080/static/index.html?token=s3cr3t", "extractor": None,
                  "max_depth": 2, "max_pages": 30, "allowed_domains": ["mock-site"]}
    raw_error = ("Seed URL https://admin:hunter2@mock-site:8080/static/index.html?token=s3cr3t cannot be crawled: "
                 "mock-site resolves to a private or reserved address.")
    with session_scope() as session:
        job = BackgroundJob(type="crawl", status="failed", params=raw_params, error_message=raw_error)
        session.add(job)
        session.flush()
        job_id = job.background_job_id
        progress.add_log(session, job_id, "INFO", "Crawl started: http://mock-site:8080/static/index.html "
                         "(max_depth 2, max_pages 30, allowed domains mock-site)", url="http://mock-site:8080/static/index.html")
        progress.add_log(session, job_id, "INFO", "Loaded robots.txt for mock-site", host="mock-site", crawl_delay=1.0)
        progress.add_log(session, job_id, "WARNING", "Connection error on attempt 1/3 for http://10.0.0.8/jobs, "
                         "retrying in 1.0 s", attempt=1)
        progress.add_log(session, job_id, "ERROR", 'Failed /data/uploads/x.pdf for asha.verma@example.com +91 98765 43210\n'
                         'Traceback (most recent call last):\n  File "/app/app/worker/tasks.py", line 1')
        progress.add_log(session, job_id, "INFO", "Fetched https://jobs.example.com/careers (200): 3 jobs extracted, "
                         "3 saved (3 new, 0 updated), 5 new links", url="https://jobs.example.com/careers",
                         upload_id="f00dbabe-2b3c-4d4e-9f5a-6b7c8d9e0f1a", stored_file="f00dbabe.pdf", jobs_saved=3)

    detail = api.get(f"/background-jobs/{job_id}").json()
    assert detail["params"] == {"seed_url": f"https://{INTERNAL}/static/index.html?token=[redacted]", "extractor": None,
                                "max_depth": 2, "max_pages": 30, "allowed_domains": [INTERNAL]}
    assert detail["error_message"] == (f"Seed URL https://{INTERNAL}/static/index.html?token=[redacted] cannot be "
                                       f"crawled: {INTERNAL} resolves to a private or reserved address.")
    items = api.get(f"/background-jobs/{job_id}/logs").json()["items"]
    assert [i["message"] for i in items] == [
        f"Crawl started: http://{INTERNAL}/static/index.html (max_depth 2, max_pages 30, allowed domains {INTERNAL})",
        f"Loaded robots.txt for {INTERNAL}",
        "Connection error on attempt 1/3 for http://[IP address]/jobs, retrying in 1.0 s",
        "Failed [path] for [email] [number] [details removed]",
        "Fetched https://jobs.example.com/careers (200): 3 jobs extracted, 3 saved (3 new, 0 updated), 5 new links",
    ]
    assert [i.get("context") for i in items] == [
        {"url": f"http://{INTERNAL}/static/index.html"}, {"host": INTERNAL, "crawl_delay": 1.0}, {"attempt": 1}, None,
        {"url": "https://jobs.example.com/careers", "upload_id": "f00dbabe", "jobs_saved": 3}]
    shown = str(detail) + str(items)
    for secret in ("hunter2", "admin", "s3cr3t", "mock-site", "10.0.0.8", "/data/uploads", "asha", "98765",
                   "Traceback", "/app/app", "stored_file", "2b3c-4d4e"):
        assert secret not in shown, secret

    # Only what the API shows is redacted: the stored record is exactly what the worker wrote.
    stored = load(job_id)
    assert stored.params == raw_params and stored.error_message == raw_error
    with SessionLocal() as session:
        stored_logs = session.execute(select(BackgroundJobLog).where(BackgroundJobLog.background_job_id == job_id)
                                      .order_by(BackgroundJobLog.log_id)).scalars().all()
    assert stored_logs[1].message == "Loaded robots.txt for mock-site" and stored_logs[1].context["host"] == "mock-site"
    assert stored_logs[4].context["stored_file"] == "f00dbabe.pdf"


def test_logs_are_timestamped_ordered_and_incremental(api):
    job_id = make_job("running")
    with session_scope() as s:
        for level, message in [("DEBUG", "d"), ("INFO", "i1"), ("WARNING", "w"), ("INFO", "i2"), ("ERROR", "e")]:
            progress.add_log(s, job_id, level, message, url="https://jobs.example.com/" if level == "WARNING" else None)
    body = api.get(f"/background-jobs/{job_id}/logs").json()
    assert [i["message"] for i in body["items"]] == ["d", "i1", "w", "i2", "e"]
    assert all(i["created_at"] for i in body["items"])
    assert body["items"][2]["context"] == {"url": "https://jobs.example.com/"} and "context" not in body["items"][0]
    second = body["items"][1]["log_id"]
    newer = api.get(f"/background-jobs/{job_id}/logs?after_id={second}").json()
    assert [i["message"] for i in newer["items"]] == ["w", "i2", "e"] and newer["next_after_id"] == body["next_after_id"]
    warnings = api.get(f"/background-jobs/{job_id}/logs?level=WARNING").json()
    assert [i["level"] for i in warnings["items"]] == ["WARNING", "ERROR"]
    empty = api.get(f"/background-jobs/{job_id}/logs?after_id={body['next_after_id']}").json()
    assert empty == {"items": [], "next_after_id": body["next_after_id"]}
    assert api.get(f"/background-jobs/{uuid.uuid4()}/logs").status_code == 404


def test_logs_belong_to_their_job_and_are_returned_in_pages(app_db):
    first, second = make_job("running"), make_job("running")
    with session_scope() as s:
        for i in range(5):
            progress.add_log(s, first, "INFO", f"first {i}")
        progress.add_log(s, second, "INFO", "second")
    with SessionLocal() as s:
        items, next_after_id = service.get_logs(s, first, after_id=0, min_level=None, limit=3)
        assert [i.message for i in items] == ["first 0", "first 1", "first 2"]
        items, _ = service.get_logs(s, first, after_id=next_after_id, min_level=None, limit=3)
        assert [i.message for i in items] == ["first 3", "first 4"]


# --- Stale-job checks (LLD §5.8, §9.8) -------------------------------------------------------------


def test_running_job_with_an_old_heartbeat_is_failed(app_db):
    stale, alive = make_job("running"), make_job("running")
    set_times(stale, heartbeat_at=601)
    set_times(alive, heartbeat_at=30)
    with SessionLocal() as s:
        assert service.fail_stale_jobs(s) == (1, 0)
    job = load(stale)
    assert (job.status, job.error_message) == ("failed", "Worker stopped unexpectedly.") and job.finished_at
    assert load(alive).status == "running"
    assert ("ERROR", "Worker stopped unexpectedly.") in logs_of(stale)


def test_queued_job_never_picked_up_is_failed(app_db):
    old_a, old_b, young = make_job("queued"), make_job("queued"), make_job("queued")
    set_times(old_a, created_at=660)
    set_times(old_b, created_at=700)
    with SessionLocal() as s:
        assert service.fail_stale_jobs(s) == (0, 2)  # failing one does not count as worker activity
    message = ("No worker picked up this job within 10 minutes. "
               "The worker may be stopped, or the task was lost. Start it again.")
    assert load(old_a).error_message == message and load(old_b).status == "failed"
    assert load(young).status == "queued"


def test_queued_job_waiting_behind_a_running_job_is_left_alone(app_db):
    waiting, busy = make_job("queued"), make_job("running")
    set_times(waiting, created_at=900)
    set_times(busy, heartbeat_at=20)  # the worker is busy with a long crawl
    with SessionLocal() as s:
        assert service.fail_stale_jobs(s) == (0, 0)
    assert load(waiting).status == "queued"


def test_stale_check_is_idempotent_and_runs_when_jobs_are_listed(api):
    job_id = make_job("running")
    set_times(job_id, heartbeat_at=3600)
    items = api.get("/background-jobs").json()["items"]
    assert items[0]["status"] == "failed"
    with SessionLocal() as s:
        assert service.fail_stale_jobs(s) == (0, 0)
    assert [m for _, m in logs_of(job_id)].count("Worker stopped unexpectedly.") == 1


def test_stale_check_message_uses_the_configured_timeout(app_db, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "job_queued_timeout_seconds", 90)
    job_id = make_job("queued")
    set_times(job_id, created_at=120)
    with SessionLocal() as s:
        service.fail_stale_jobs(s)
    assert load(job_id).error_message.startswith("No worker picked up this job within 90 seconds.")


# --- Worker failure handling ----------------------------------------------------------------------------


def _with_params(job_id):
    with session_scope() as s:
        s.execute(text("UPDATE background_jobs SET params = CAST(:p AS jsonb) WHERE background_job_id = :id"),
                  {"p": '{"seed_url": "https://jobs.example.com/", "max_depth": 1, "max_pages": 5, '
                        '"allowed_domains": ["jobs.example.com"], "extractor": null}', "id": job_id})
    return job_id


@pytest.mark.parametrize(
    ("error", "message"),
    [(RuntimeError("database went away"), "Unexpected error during the crawl (RuntimeError). Jobs saved so far are kept."),
     (SoftTimeLimitExceeded(), "Time limit exceeded.")],
)
def test_task_failures_end_the_job_as_failed(app_db, monkeypatch, error, message):
    job_id = _with_params(make_job("queued", progress_total=5))

    def explode(*args, **kwargs):
        raise error

    monkeypatch.setattr(tasks, "build_crawler", explode)
    assert tasks.run_crawl_job(job_id) == "failed"
    job = load(job_id)
    assert (job.status, job.error_message) == ("failed", message) and job.finished_at
    assert logs_of(job_id)[-1][0] == "ERROR"


def test_task_for_a_job_that_is_not_queued_does_nothing(app_db):
    job_id = make_job("cancelled")
    assert tasks.run_crawl_job(job_id) == "not-claimed"
    assert tasks.run_crawl_job(uuid.uuid4()) == "not-claimed"
    assert load(job_id).status == "cancelled" and logs_of(job_id) == []
