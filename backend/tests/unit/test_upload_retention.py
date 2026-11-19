"""Upload retention rules, without a database (LLD §6.10). The database part is in tests/integration."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.services import upload_retention as retention
from app.services.upload_retention import DELETE, KEEP, StoredFile, UploadState, decide, parse_name

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


def an_id() -> str:
    return str(uuid.uuid4())


def file(upload_id: str, kind: str = "pdf", age: timedelta = timedelta(days=30)) -> StoredFile:
    suffix = {"pdf": ".pdf", "json": ".json", "part": ".part"}[kind]
    return StoredFile(upload_id + suffix, upload_id, kind, NOW - age)


# --- File names -----------------------------------------------------------------------------------

def test_only_uuid_named_files_are_considered():
    upload_id = an_id()
    assert [parse_name(upload_id + ext) for ext in (".pdf", ".json", ".part", ".json.part")] == [
        (upload_id, "pdf"), (upload_id, "json"), (upload_id, "part"), (upload_id, "part")]
    for name in (upload_id.upper() + ".pdf", "cv.pdf", upload_id + ".txt", "../" + upload_id + ".pdf",
                 upload_id + ".pdf.bak", "README.md", upload_id):
        assert parse_name(name) is None


# --- The rules --------------------------------------------------------------------------------------

def test_files_of_a_queued_or_running_job_are_never_deleted():
    upload_id = an_id()
    state = UploadState(active={upload_id}, referenced={upload_id})
    for kind in ("pdf", "json", "part"):
        assert decide(file(upload_id, kind, timedelta(days=365)), state, NOW) == (KEEP, "job still queued or running")


def test_a_candidates_current_pdf_is_kept_but_its_metadata_goes_once_the_job_finished():
    upload_id = an_id()
    state = UploadState(finished={upload_id: NOW - timedelta(days=400)}, referenced={upload_id})
    assert decide(file(upload_id, "pdf"), state, NOW) == (KEEP, "current PDF of a candidate")
    assert decide(file(upload_id, "json"), state, NOW) == (DELETE, "metadata of a parsed candidate (job finished)")


@pytest.mark.parametrize(("finished_ago", "action"), [(timedelta(days=8), DELETE), (timedelta(days=6), KEEP),
                                                      (timedelta(days=7, seconds=1), DELETE)])
def test_a_finished_job_without_a_candidate_waits_7_days(finished_ago, action):
    upload_id = an_id()
    state = UploadState(finished={upload_id: NOW - finished_ago})
    for kind in ("pdf", "json"):
        assert decide(file(upload_id, kind, age=timedelta(days=300)), state, NOW)[0] == action  # job time counts, not file age


@pytest.mark.parametrize(("age", "action"), [(timedelta(days=2), DELETE), (timedelta(hours=2), KEEP)])
def test_files_in_no_job_wait_1_day(age, action):
    state = UploadState()
    for kind in ("pdf", "json"):
        assert decide(file(an_id(), kind, age), state, NOW)[0] == action


@pytest.mark.parametrize(("age", "action"), [(timedelta(hours=2), DELETE), (timedelta(minutes=30), KEEP)])
def test_interrupted_copies_wait_1_hour(age, action):
    assert decide(file(an_id(), "part", age), UploadState(), NOW)[0] == action


def test_metadata_of_a_referenced_upload_without_any_job_falls_back_to_the_1_day_rule():
    upload_id = an_id()
    state = UploadState(referenced={upload_id})
    assert decide(file(upload_id, "json", timedelta(hours=3)), state, NOW)[0] == KEEP
    assert decide(file(upload_id, "json", timedelta(days=3)), state, NOW)[0] == DELETE


# --- Running against a folder ---------------------------------------------------------------------

@pytest.fixture
def folder(tmp_path):
    """Files for every category; the database state is given directly (no database here)."""
    ids = {name: an_id() for name in ("active", "candidate", "old_failed", "recent_failed", "orphan_old", "orphan_new")}
    ages = {"active": 40, "candidate": 40, "old_failed": 40, "recent_failed": 40, "orphan_old": 2, "orphan_new": 0.01}
    for key, upload_id in ids.items():
        for ext in (".pdf", ".json"):
            path = tmp_path / f"{upload_id}{ext}"
            path.write_bytes(b"x")
            stamp = (NOW - timedelta(days=ages[key])).timestamp()
            os.utime(path, (stamp, stamp))
    old_part = tmp_path / f"{an_id()}.part"
    old_part.write_bytes(b"x")
    os.utime(old_part, ((NOW - timedelta(hours=3)).timestamp(),) * 2)
    new_part = tmp_path / f"{an_id()}.json.part"
    new_part.write_bytes(b"x")
    os.utime(new_part, ((NOW - timedelta(minutes=10)).timestamp(),) * 2)
    (tmp_path / "notes.txt").write_text("not ours")
    (tmp_path / "subfolder").mkdir()
    (tmp_path / f"{an_id().upper()}.pdf").write_bytes(b"x")  # not a canonical UUID name
    state = UploadState(active={ids["active"]},
                        finished={ids["candidate"]: NOW - timedelta(days=30), ids["old_failed"]: NOW - timedelta(days=9),
                                  ids["recent_failed"]: NOW - timedelta(days=1)},
                        referenced={ids["candidate"]})
    return tmp_path, ids, state


def names(path) -> set[str]:
    return {p.name for p in path.iterdir()}


def run(folder_path, state, monkeypatch, delete):
    monkeypatch.setattr(retention, "load_state", lambda session: state)
    return retention.run(session=None, upload_dir=folder_path, delete=delete, now=NOW)


def test_a_dry_run_deletes_nothing_and_reports_counts(folder, monkeypatch):
    path, ids, state = folder
    before = names(path)
    report = run(path, state, monkeypatch, delete=False)
    assert names(path) == before
    assert (report.dry_run, report.deleted, report.unexpected) == (True, 0, 3)
    assert dict(report.to_delete) == {
        "metadata of a parsed candidate (job finished)": 1,
        "finished job without a candidate, finished over 7 days ago": 2,
        "in no job, older than 1 day": 2,
        "interrupted copy, older than 1 hour": 1,
    }
    assert dict(report.kept) == {
        "job still queued or running": 2,
        "current PDF of a candidate": 1,
        "finished job without a candidate, finished under 7 days ago": 2,
        "in no job, younger than 1 day": 2,
        "interrupted copy, younger than 1 hour": 1,
    }


def test_delete_removes_exactly_the_planned_files_and_a_second_run_does_nothing(folder, monkeypatch):
    path, ids, state = folder
    report = run(path, state, monkeypatch, delete=True)
    assert (report.deleted, report.errors, report.already_gone) == (6, 0, 0)
    left = names(path)
    for key in ("active", "recent_failed", "orphan_new"):
        assert {f"{ids[key]}.pdf", f"{ids[key]}.json"} <= left
    assert f"{ids['candidate']}.pdf" in left and f"{ids['candidate']}.json" not in left
    for key in ("old_failed", "orphan_old"):
        assert not {f"{ids[key]}.pdf", f"{ids[key]}.json"} & left
    assert {"notes.txt", "subfolder"} <= left  # unexpected entries are never touched
    again = run(path, state, monkeypatch, delete=True)
    assert (again.deleted, sum(again.to_delete.values())) == (0, 0)  # idempotent


def test_a_file_that_disappears_before_deletion_is_fine(folder, monkeypatch):
    path, ids, state = folder
    real_delete = retention._delete

    def someone_else_deleted_it_first(upload_dir, name):
        (upload_dir / name).unlink(missing_ok=True)
        return real_delete(upload_dir, name)
    monkeypatch.setattr(retention, "_delete", someone_else_deleted_it_first)
    report = run(path, state, monkeypatch, delete=True)
    assert (report.deleted, report.already_gone, report.errors) == (0, 6, 0)


def test_deletion_refuses_names_that_are_not_expected(tmp_path):
    victim = tmp_path / "keep-me.pdf"
    victim.write_bytes(b"x")
    assert retention._delete(tmp_path, "keep-me.pdf") == "error"
    assert retention._delete(tmp_path, f"../{tmp_path.name}/keep-me.pdf") == "error"
    assert victim.exists()


def test_a_missing_upload_folder_is_an_empty_report(tmp_path, monkeypatch):
    report = run(tmp_path / "missing", UploadState(), monkeypatch, delete=True)
    assert (sum(report.files.values()), report.deleted, report.unexpected) == (0, 0, 0)


def test_the_report_has_counts_only(folder, monkeypatch):
    path, ids, state = folder
    lines = retention.format_report(run(path, state, monkeypatch, delete=False))
    text = "\n".join(lines)
    assert "6 files would be deleted. Run again with --delete to delete them." in text
    assert not any(upload_id in text for upload_id in ids.values()) and ".pdf" not in text
