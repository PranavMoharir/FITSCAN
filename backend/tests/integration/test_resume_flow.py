"""End to end, offline: upload -> UUID storage -> resume job -> Celery task -> parsing -> PostgreSQL (LLD §9.8).

Celery runs the real `resume` task in this process (`Task.apply`), so the API, the task, the
parser and the database run exactly as in production, without Redis. The resumes are synthetic
PDFs (tests/resume_pdfs.py); "today" is fixed at 18 November 2026. OCR is replaced where a test
needs it, so the results are the same with or without Tesseract installed.
"""

import json
import logging
import uuid
from dataclasses import replace
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models import BackgroundJob, BackgroundJobLog, Candidate, CandidateSkill, Skill
from app.resumes import ocr
from app.services import background_jobs as service
from app.worker import tasks
from app.worker.celery_app import celery_app
from tests import resume_pdfs
from tests.resume_pdfs import PEOPLE

PDF = "application/pdf"
# Personal details of the synthetic people and their file names: none may ever appear in a log.
PRIVATE = ["Asha", "Verma", "Rahul", "Mehta", "Meera", "Iyer", "example.com", "98765", "91234", "99887",
           "Asha_Verma_CV", "Rahul-Mehta", "meera_iyer", "Savitribai", "Built REST APIs", "Initech"]
# Kept out of the test's source lines: tracebacks in the server log show code lines (never messages).
QUOTED_PERSONAL_DATA = f"{PEOPLE['asha'].email} {PEOPLE['asha'].phone}"


@pytest.fixture
def env(app_db, monkeypatch, tmp_path):
    """Uploads go to tmp_path; publishing runs the task at once (or later, with run_later=True)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(tasks, "current_date", lambda: date(2026, 11, 18))
    monkeypatch.setattr(ocr, "tesseract_version", lambda: None)
    state = {"run_later": False, "queued": [], "before_task": None}

    def publish(name, job_id):
        if state["run_later"]:
            state["queued"].append((name, job_id))
            return "task-later"
        if state["before_task"]:
            state["before_task"](job_id)
        return celery_app.tasks[name].apply(args=[str(job_id)]).id
    monkeypatch.setattr(service, "publish_task", publish)
    monkeypatch.setattr(service, "revoke_task", lambda task_id: None)
    state["api"] = TestClient(app)
    state["dir"] = settings.upload_dir
    return state


def upload(env, *files):
    return env["api"].post("/background-jobs/resume", files=[("files", f) for f in files])


def job_row(job_id) -> BackgroundJob:
    with SessionLocal() as session:
        return session.get(BackgroundJob, job_id)


def logs(job_id) -> list[BackgroundJobLog]:
    with SessionLocal() as session:
        return list(session.execute(select(BackgroundJobLog).where(BackgroundJobLog.background_job_id == job_id)
                                    .order_by(BackgroundJobLog.log_id)).scalars())


def messages(job_id) -> list[str]:
    return [line.message for line in logs(job_id)]


def candidates() -> list[Candidate]:
    with SessionLocal() as session:
        return list(session.execute(select(Candidate).order_by(Candidate.name)).scalars())


def skills_of(candidate_id) -> set[str]:
    with SessionLocal() as session:
        return set(session.execute(select(Skill.canonical_name).join(CandidateSkill, CandidateSkill.skill_id == Skill.skill_id)
                                   .where(CandidateSkill.candidate_id == candidate_id)).scalars())


def assert_no_personal_data(job_ids, caplog=None):
    texts = []
    for job_id in job_ids:
        texts += [line.message + " " + json.dumps(line.context or {}) for line in logs(job_id)]
        texts.append(job_row(job_id).error_message or "")
    if caplog is not None:
        texts += [record.getMessage() for record in caplog.records]
    leaks = [(secret, text) for text in texts for secret in PRIVATE if secret.lower() in text.lower()]
    assert leaks == []


# --- The whole pipeline ---------------------------------------------------------------------------


def test_upload_parses_every_file_and_saves_candidates(env, caplog):
    caplog.set_level(logging.DEBUG)
    response = upload(env,
                      ("Asha_Verma_CV.pdf", resume_pdfs.one_column(), PDF),
                      ("Rahul-Mehta two column.pdf", resume_pdfs.two_column(PEOPLE["rahul"]), PDF),
                      ("meera_iyer_table.pdf", resume_pdfs.table(PEOPLE["meera"]), PDF),
                      ("locked.pdf", resume_pdfs.encrypted(), PDF),
                      ("broken.pdf", resume_pdfs.corrupt(), PDF),
                      ("notes.txt", b"not a resume", "text/plain"))
    assert response.status_code == 202
    body = response.json()
    assert body["type"] == "resume" and body["status"] == "queued"
    assert body["progress"] == {"current": 0, "total": 5, "percent": 0}
    # Files are identified by their position in the request and their upload ID; no name is returned.
    assert [item["index"] for item in body["accepted_files"]] == [0, 1, 2, 3, 4]
    assert [set(item) for item in body["accepted_files"]] == [{"index", "upload_id", "size_bytes"}] * 5
    assert body["rejected_files"] == [{"index": 5, "code": "NOT_A_PDF", "message": "File is not a PDF document."}]
    assert not [name for name in ("Asha_Verma_CV", "Rahul-Mehta", "meera_iyer", "locked", "broken", "notes")
                if name in response.text]
    job_id = body["background_job_id"]

    # Files are stored under their upload IDs only. The job's params hold upload IDs and generated
    # storage names, never the original names (GET /background-jobs/{id} returns params).
    job = job_row(job_id)
    params = job.params["files"]
    assert [set(item) for item in params] == [{"upload_id", "stored_file", "size_bytes"}] * 5
    assert [item["stored_file"] for item in params] == [f"{item['upload_id']}.pdf" for item in params]
    assert [a["upload_id"] for a in body["accepted_files"]] == [item["upload_id"] for item in params]
    assert [a["size_bytes"] for a in body["accepted_files"]] == [item["size_bytes"] for item in params]
    assert sorted(p.name for p in env["dir"].iterdir()) == sorted(
        f"{item['upload_id']}.{ext}" for item in params for ext in ("pdf", "json"))
    detail = env["api"].get(f"/background-jobs/{job_id}").text
    assert not [name for name in ("Asha_Verma_CV", "Rahul-Mehta", "meera_iyer", "locked", "broken") if name in detail]

    # Progress, counters and the final state: one bad file never stops the others.
    assert job.status == "completed" and job.started_at and job.finished_at and job.heartbeat_at
    assert (job.progress_current, job.progress_total, job.items_succeeded, job.items_failed) == (5, 5, 3, 2)
    assert env["api"].get(f"/background-jobs/{job_id}").json()["progress"] == {"current": 5, "total": 5, "percent": 100}

    saved = {c.name: c for c in candidates()}
    assert set(saved) == {"Asha Verma", "Rahul Mehta", "Meera Iyer"}
    asha = saved["Asha Verma"]
    assert (asha.email, asha.phone, asha.city, asha.current_title) == (
        "asha.verma@example.com", "+919876543210", "Pune", "Senior Backend Engineer")
    assert asha.source_file == "Asha_Verma_CV.pdf" and asha.stored_path == f"{params[0]['upload_id']}.pdf"
    assert asha.background_job_id == uuid.UUID(job_id) and asha.parsed_with_ocr is False
    assert "Acme Analytics" in asha.resume_text
    assert {"Python", "Go", "FastAPI", "PostgreSQL", "Docker"} <= skills_of(asha.candidate_id)
    assert {"C#", ".NET", "R", "AWS"} <= skills_of(saved["Meera Iyer"].candidate_id)  # from the table cells
    assert saved["Rahul Mehta"].city == "Bengaluru"

    lines = messages(job_id)
    short = [item["upload_id"][:8] for item in params]
    assert lines[0] == "Resume parsing started: 5 files."
    assert f"Resume upload {short[0]}: parsed (created a new candidate)." in lines
    assert f"Resume upload {short[3]} failed: the file is password-protected." in lines
    assert f"Resume upload {short[4]} failed: the file is damaged or not a valid PDF." in lines
    assert ("Resume parsing finished: 5 of 5 files processed (3 new candidates, 0 updated, "
            "0 duplicates skipped, 2 failed).") in lines
    parsed_line = next(l for l in logs(job_id) if l.message.startswith(f"Resume upload {short[0]}: parsed"))
    assert parsed_line.context["upload_id"] == params[0]["upload_id"] and parsed_line.context["pages"] == 1
    assert_no_personal_data([job_id], caplog)


def test_no_acceptable_file_gives_422_and_creates_no_job(env):
    response = upload(env, ("notes.txt", b"hello", "text/plain"))
    assert response.status_code == 422 and response.json()["error"]["code"] == "NO_VALID_FILES"
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(BackgroundJob)) == 0
    assert not env["dir"].exists() or list(env["dir"].iterdir()) == []


def test_the_same_file_twice_is_skipped_as_a_duplicate(env):
    pdf = resume_pdfs.one_column()
    first = upload(env, ("Asha_Verma_CV.pdf", pdf, PDF), ("copy.pdf", pdf, PDF)).json()["background_job_id"]
    job = job_row(first)
    assert (job.status, job.progress_current, job.items_succeeded, job.items_failed) == ("completed", 2, 1, 0)
    assert any(m.endswith(": duplicate file, skipped (an existing candidate has the same file).") for m in messages(first))

    second = upload(env, ("again.pdf", pdf, PDF)).json()["background_job_id"]
    job = job_row(second)
    assert job.status == "failed"
    assert job.error_message == "No candidate was saved: every file was a duplicate of an existing candidate."
    assert len(candidates()) == 1


def test_a_new_resume_with_the_same_email_updates_the_candidate(env):
    upload(env, ("Asha_Verma_CV.pdf", resume_pdfs.one_column(), PDF))
    newer = replace(PEOPLE["asha"], title="Staff Engineer", email="ASHA.VERMA@example.com",
                    skills="Rust, Python, Kubernetes")
    job_id = upload(env, ("Asha_Verma_CV_2026.pdf", resume_pdfs.one_column(newer), PDF)).json()["background_job_id"]
    [asha] = candidates()
    assert (asha.current_title, asha.source_file) == ("Staff Engineer", "Asha_Verma_CV_2026.pdf")
    assert asha.background_job_id == uuid.UUID(job_id)
    assert "Rust" in skills_of(asha.candidate_id)
    assert any("updated the existing candidate with the same email" in m for m in messages(job_id))


def test_malformed_optional_fields_are_saved_as_warnings(env):
    person = replace(PEOPLE["asha"], email="asha.verma@example", phone="Phone: 12345")
    upload(env, ("cv.pdf", resume_pdfs.one_column(person), PDF))
    [asha] = candidates()
    assert (asha.email, asha.phone) == (None, None)
    assert asha.parse_warnings == ["invalid email removed", "invalid phone removed"]


# --- OCR ------------------------------------------------------------------------------------------


def test_a_scanned_resume_without_tesseract_is_flagged_and_not_saved(env):
    job_id = upload(env, ("scan.pdf", resume_pdfs.scanned(), PDF)).json()["background_job_id"]
    job = job_row(job_id)
    assert (job.status, job.items_failed, job.error_message) == ("failed", 1, "All 1 files failed.")
    by_level = [(line.level, line.message.split(": ", 1)[1]) for line in logs(job_id) if line.message.startswith("Resume upload")]
    assert by_level == [("WARNING", "page 1 is scanned and OCR produced no text (Tesseract is not installed)."),
                        ("WARNING", "scanned resume: OCR produced no text, so no candidate was created.")]
    assert [l.context.get("page") for l in logs(job_id) if "page 1 is scanned" in l.message] == [1]
    assert candidates() == []


def test_a_scanned_resume_read_by_ocr_is_saved_with_parsed_with_ocr(env, monkeypatch):
    monkeypatch.setattr(ocr, "ocr_page", lambda page, **kw: (
        "KIRAN RAO\nkiran.rao@example.com | Hyderabad\n\nSkills\nPython, Go, Kubernetes\n\n"
        "Experience\nPlatform Engineer, Hooli (Mar 2022 - Present)\n"))
    job_id = upload(env, ("scan.pdf", resume_pdfs.scanned(), PDF)).json()["background_job_id"]
    [kiran] = candidates()
    assert kiran.parsed_with_ocr is True and kiran.name == "Kiran Rao"
    assert skills_of(kiran.candidate_id) == {"Python", "Go", "Kubernetes"}
    lines = messages(job_id)
    assert any(": page 1: OCR completed (" in m for m in lines)
    assert any(m.endswith("parsed (created a new candidate, OCR on page 1).") for m in lines)


# --- Job control ----------------------------------------------------------------------------------


def test_cancelling_between_files_keeps_what_was_saved(env, monkeypatch):
    real = tasks.process_resume_file

    def process_then_cancel(run, item, *args):
        real(run, item, *args)
        with SessionLocal() as session:  # the user presses Cancel while the first file is processed
            service.cancel_job(session, run.job_id)
    monkeypatch.setattr(tasks, "process_resume_file", process_then_cancel)
    job_id = upload(env, ("a.pdf", resume_pdfs.one_column(), PDF),
                    ("b.pdf", resume_pdfs.two_column(PEOPLE["rahul"]), PDF),
                    ("c.pdf", resume_pdfs.table(PEOPLE["meera"]), PDF)).json()["background_job_id"]
    job = job_row(job_id)
    assert (job.status, job.progress_current, job.items_succeeded) == ("cancelled", 1, 1)
    assert [c.name for c in candidates()] == ["Asha Verma"]
    assert "Cancelled by user after 1 items." in messages(job_id)


def test_a_job_cancelled_while_queued_is_never_processed(env):
    env["run_later"] = True
    job_id = upload(env, ("a.pdf", resume_pdfs.one_column(), PDF)).json()["background_job_id"]
    assert env["api"].post(f"/background-jobs/{job_id}/cancel").json() == {"status": "cancelled"}
    name, queued_id = env["queued"][0]
    assert celery_app.tasks[name].apply(args=[str(queued_id)]).get() == "not-claimed"
    assert job_row(job_id).status == "cancelled" and candidates() == []


def test_a_job_ended_elsewhere_is_never_overwritten(env, monkeypatch):
    real = tasks.process_resume_file

    def fail_the_job_meanwhile(run, item, *args):
        real(run, item, *args)
        with SessionLocal() as session:  # e.g. the stale-job check decided the worker was lost
            session.execute(update(BackgroundJob).where(BackgroundJob.background_job_id == run.job_id)
                            .values(status="failed", error_message="Worker stopped unexpectedly."))
            session.commit()
    monkeypatch.setattr(tasks, "process_resume_file", fail_the_job_meanwhile)
    job_id = upload(env, ("a.pdf", resume_pdfs.one_column(), PDF), ("b.pdf", resume_pdfs.table(), PDF)).json()["background_job_id"]
    job = job_row(job_id)
    assert (job.status, job.error_message, job.progress_current) == ("failed", "Worker stopped unexpectedly.", 0)


def test_a_missing_stored_file_fails_only_that_file(env):
    def delete_first(job_id):
        first = job_row(job_id).params["files"][0]["upload_id"]
        (env["dir"] / f"{first}.pdf").unlink()
    env["before_task"] = delete_first
    job_id = upload(env, ("a.pdf", resume_pdfs.one_column(), PDF), ("b.pdf", resume_pdfs.table(PEOPLE["meera"]), PDF)
                    ).json()["background_job_id"]
    job = job_row(job_id)
    assert (job.status, job.items_succeeded, job.items_failed) == ("completed", 1, 1)
    assert any(m.endswith("failed: the stored file is missing from the uploads volume.") for m in messages(job_id))


def test_a_missing_metadata_file_only_loses_the_original_name(env):
    def delete_metadata(job_id):
        first = job_row(job_id).params["files"][0]["upload_id"]
        (env["dir"] / f"{first}.json").unlink()
    env["before_task"] = delete_metadata
    job_id = upload(env, ("Asha_Verma_CV.pdf", resume_pdfs.one_column(), PDF)).json()["background_job_id"]
    [asha] = candidates()
    assert (asha.name, asha.source_file) == ("Asha Verma", "unnamed.pdf")
    assert any(m.endswith(": the original file name is not available; 'unnamed.pdf' is used.") for m in messages(job_id))


def test_an_unreadable_uploads_volume_fails_the_job(env, monkeypatch, tmp_path):
    env["before_task"] = lambda job_id: monkeypatch.setattr(get_settings(), "upload_dir", tmp_path / "missing")
    job_id = upload(env, ("a.pdf", resume_pdfs.one_column(), PDF)).json()["background_job_id"]
    job = job_row(job_id)
    assert (job.status, job.error_message) == ("failed", "The uploads volume is not readable, so no file could be processed.")


def test_broker_down_marks_the_job_failed_and_removes_the_stored_files(env, monkeypatch):
    def broker_down(name, job_id):
        raise ConnectionError("redis is down")
    monkeypatch.setattr(service, "publish_task", broker_down)
    response = upload(env, ("a.pdf", resume_pdfs.one_column(), PDF))
    assert response.status_code == 503 and response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    with SessionLocal() as session:
        job = session.execute(select(BackgroundJob)).scalar_one()
    assert (job.type, job.status) == ("resume", "failed")
    assert list(env["dir"].iterdir()) == []


def test_unknown_skill_terms_are_reported_without_personal_details(env):
    person = replace(PEOPLE["asha"], skills="Python, Looker Studio, Verma Toolkit, Go")
    job_id = upload(env, ("Asha_Verma_CV.pdf", resume_pdfs.one_column(person), PDF)).json()["background_job_id"]
    assert "Skill-like terms not in the taxonomy: looker studio (1)" in messages(job_id)
    assert_no_personal_data([job_id])


def test_every_log_line_of_every_outcome_is_free_of_personal_data(env, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    pdf = resume_pdfs.one_column()
    ids = [upload(env, ("Asha_Verma_CV.pdf", pdf, PDF), ("Asha_Verma_CV copy.pdf", pdf, PDF),
                  ("meera_iyer_scan.pdf", resume_pdfs.scanned(PEOPLE["meera"]), PDF),
                  ("Rahul-Mehta locked.pdf", resume_pdfs.encrypted(PEOPLE["rahul"]), PDF)).json()["background_job_id"]]

    def explode(*args, **kwargs):
        raise ValueError(QUOTED_PERSONAL_DATA)  # an error whose message quotes personal data
    monkeypatch.setattr(tasks, "parse_resume", explode)
    ids.append(upload(env, ("Rahul-Mehta.pdf", resume_pdfs.two_column(PEOPLE["rahul"]), PDF)).json()["background_job_id"])
    assert any("failed: unexpected error (ValueError)." in m for m in messages(ids[1]))
    assert_no_personal_data(ids, caplog)
