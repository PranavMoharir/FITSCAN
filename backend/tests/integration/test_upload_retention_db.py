"""Upload retention with real database state: the command itself, dry run and --delete (LLD §6.10)."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.db.session import SessionLocal
from app.models import BackgroundJob, BackgroundJobLog, Candidate
from app.services import upload_retention
from tests.integration.helpers import make_candidate


@pytest.fixture
def uploads(app_db, tmp_path, monkeypatch):
    """Jobs and candidates in PostgreSQL, and their files on disk, for every retention category."""
    folder = tmp_path / "uploads"
    folder.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", folder)
    now = datetime.now(UTC)
    ids = {key: str(uuid.uuid4()) for key in (
        "queued", "running", "parsed_old", "parsed_recent", "failed_old", "failed_recent", "superseded_old",
        "orphan_old", "orphan_new")}

    def job(status, files, finished_days_ago=None):
        finished = now - timedelta(days=finished_days_ago) if finished_days_ago is not None else None
        return BackgroundJob(type="resume", status=status, finished_at=finished,
                             params={"files": [{"upload_id": ids[f], "stored_file": f"{ids[f]}.pdf", "size_bytes": 1}
                                               for f in files]})

    with SessionLocal() as session:
        session.add_all([
            job("queued", ["queued"]),
            job("running", ["running"]),
            job("completed", ["parsed_old", "failed_old", "superseded_old"], finished_days_ago=10),
            job("completed", ["parsed_recent", "failed_recent"], finished_days_ago=2),
        ])
        # The candidate of "superseded_old" was updated by a newer resume, so it now points at parsed_old.
        session.add_all([make_candidate(stored_path=f"{ids['parsed_old']}.pdf", email="a@example.com"),
                         make_candidate(stored_path=f"{ids['parsed_recent']}.pdf", email="b@example.com"),
                         make_candidate(stored_path=None)])
        session.commit()

    for key, upload_id in ids.items():
        written = now - (timedelta(hours=2) if key == "orphan_new" else timedelta(days=12))
        for ext in (".pdf", ".json"):
            path = folder / f"{upload_id}{ext}"
            path.write_bytes(b"%PDF-1.7\n" if ext == ".pdf" else b'{"source_file": "x.pdf"}')
            os.utime(path, (written.timestamp(), written.timestamp()))
    return folder, ids


def present(folder) -> set[str]:
    return {p.name for p in folder.iterdir()}


def database_counts():
    with SessionLocal() as session:
        return tuple(session.scalar(select(func.count()).select_from(model))
                     for model in (BackgroundJob, Candidate, BackgroundJobLog))


def test_dry_run_then_delete_through_the_command(uploads, capsys):
    folder, ids = uploads
    before_files, before_rows = present(folder), database_counts()

    assert upload_retention.main([]) == 0  # dry run
    out = capsys.readouterr().out
    assert present(folder) == before_files and database_counts() == before_rows
    assert "9 PDFs, 9 metadata files, 0 interrupted copies" in out
    assert "delete     2  metadata of a parsed candidate (job finished)" in out
    assert "delete     4  finished job without a candidate, finished over 7 days ago" in out
    assert "delete     2  in no job, older than 1 day" in out
    assert "8 files would be deleted" in out
    assert not any(upload_id in out for upload_id in ids.values())

    assert upload_retention.main(["--delete"]) == 0
    assert "8 files deleted, 0 already gone, 0 errors." in capsys.readouterr().out
    left = present(folder)
    for key in ("queued", "running"):  # active jobs: everything kept
        assert {f"{ids[key]}.pdf", f"{ids[key]}.json"} <= left
    for key in ("parsed_old", "parsed_recent"):  # candidates' current PDFs kept, their metadata gone
        assert f"{ids[key]}.pdf" in left and f"{ids[key]}.json" not in left
    assert {f"{ids['failed_recent']}.pdf", f"{ids['failed_recent']}.json"} <= left  # finished 2 days ago
    assert {f"{ids['orphan_new']}.pdf", f"{ids['orphan_new']}.json"} <= left        # written 2 hours ago
    for key in ("failed_old", "superseded_old", "orphan_old"):
        assert not {f"{ids[key]}.pdf", f"{ids[key]}.json"} & left
    assert database_counts() == before_rows  # the database is only read

    assert upload_retention.main(["--delete"]) == 0  # idempotent
    assert "0 files deleted" in capsys.readouterr().out
    assert present(folder) == left
