"""Upload retention: remove uploaded files that are no longer needed (LLD §6.10).

A manual command, run in the API container (the worker sees the uploads volume read-only).
It is a dry run unless `--delete` is given, and it prints counts only:

    docker compose exec api python -m app.services.upload_retention            # dry run
    docker compose exec api python -m app.services.upload_retention --delete   # delete

Rules, decided per upload ID from PostgreSQL:

| Upload                                                    | What happens                                     |
|-----------------------------------------------------------|--------------------------------------------------|
| Its resume job is queued or running                       | Nothing, ever                                    |
| Its PDF is a candidate's current `stored_path`            | PDF kept while the candidate exists; its         |
|                                                           | metadata (.json) deleted once the job finished   |
| Finished job, no candidate uses the PDF (failed, flagged, | PDF and .json deleted 7 days after the job       |
| duplicate, cancelled, or replaced by a newer resume)      | finished                                         |
| In no job at all                                          | PDF and .json deleted 1 day after they were written |
| `<uuid>.part` / `<uuid>.json.part` (interrupted copy)     | Deleted 1 hour after it was written              |
| Any other file, folder or link                            | Never touched; counted as unexpected             |

Safety: only regular files named after a UUID, directly inside UPLOAD_DIR, are ever considered;
every path is checked again just before it is deleted; a file that is already gone is fine, so
running the command twice does no harm; the database is only read; nothing is logged but counts.
"""

import argparse
import logging
import os
import re
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BackgroundJob, Candidate

logger = logging.getLogger(__name__)

FINISHED_RETENTION = timedelta(days=7)  # files of a finished job that no candidate uses
ORPHAN_RETENTION = timedelta(days=1)    # files that belong to no job
PARTIAL_RETENTION = timedelta(hours=1)  # interrupted copies
ACTIVE_STATUSES = ("queued", "running")

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_NAME = re.compile(rf"^(?P<id>{_UUID})(?P<ext>\.pdf|\.json|\.part|\.json\.part)$")
_KIND = {".pdf": "pdf", ".json": "json", ".part": "part", ".json.part": "part"}
_STORED_PDF = re.compile(rf"^(?P<id>{_UUID})\.pdf$")

KEEP, DELETE = "keep", "delete"


@dataclass(frozen=True)
class StoredFile:
    name: str
    upload_id: str
    kind: str  # "pdf", "json" or "part"
    modified: datetime  # UTC


@dataclass
class UploadState:
    """What the database says about uploads: the only source for "active" and "referenced"."""

    active: set[str] = field(default_factory=set)                 # upload IDs of queued or running jobs
    finished: dict[str, datetime] = field(default_factory=dict)   # upload ID -> when its job finished
    referenced: set[str] = field(default_factory=set)             # upload IDs of candidates' current PDFs


@dataclass
class Report:
    dry_run: bool
    files: Counter = field(default_factory=Counter)      # kind -> count
    unexpected: int = 0                                  # entries that are never touched
    kept: Counter = field(default_factory=Counter)       # reason -> count
    to_delete: Counter = field(default_factory=Counter)  # reason -> count
    deleted: int = 0
    already_gone: int = 0
    errors: int = 0


def parse_name(name: str) -> tuple[str, str] | None:
    """(upload ID, kind) for an expected file name, otherwise None."""
    match = _NAME.match(name)
    if not match or str(uuid.UUID(match["id"])) != match["id"]:
        return None
    return match["id"], _KIND[match["ext"]]


def list_files(upload_dir: Path) -> tuple[list[StoredFile], int]:
    """The expected files directly in `upload_dir`, and how many other entries there are."""
    files, unexpected = [], 0
    if not upload_dir.is_dir():
        return files, unexpected
    with os.scandir(upload_dir) as entries:
        for entry in entries:
            parsed = parse_name(entry.name)
            if parsed is None or entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                unexpected += 1
                continue
            modified = datetime.fromtimestamp(entry.stat(follow_symlinks=False).st_mtime, tz=UTC)
            files.append(StoredFile(entry.name, parsed[0], parsed[1], modified))
    return files, unexpected


def load_state(session: Session) -> UploadState:
    state = UploadState()
    jobs = session.execute(select(BackgroundJob.status, BackgroundJob.finished_at, BackgroundJob.created_at,
                                  BackgroundJob.params).where(BackgroundJob.type == "resume"))
    for status, finished_at, created_at, params in jobs:
        files = params.get("files", []) if isinstance(params, dict) else []
        for item in files if isinstance(files, list) else []:
            upload_id = item.get("upload_id") if isinstance(item, dict) else None
            if not isinstance(upload_id, str) or parse_name(f"{upload_id}.pdf") is None:
                continue
            if status in ACTIVE_STATUSES:
                state.active.add(upload_id)
            else:
                ended = finished_at or created_at
                state.finished[upload_id] = max(ended, state.finished.get(upload_id, ended))
    for stored_path in session.scalars(select(Candidate.stored_path).where(Candidate.stored_path.is_not(None))):
        match = _STORED_PDF.match(stored_path)
        if match:
            state.referenced.add(match["id"])
    return state


def decide(file: StoredFile, state: UploadState, now: datetime) -> tuple[str, str]:
    """(KEEP or DELETE, reason) for one file. The reasons are the lines of the report."""
    upload_id = file.upload_id
    if upload_id in state.active:
        return KEEP, "job still queued or running"
    if file.kind == "part":
        if now - file.modified > PARTIAL_RETENTION:
            return DELETE, "interrupted copy, older than 1 hour"
        return KEEP, "interrupted copy, younger than 1 hour"
    if upload_id in state.referenced:
        if file.kind == "pdf":
            return KEEP, "current PDF of a candidate"
        if upload_id in state.finished:
            return DELETE, "metadata of a parsed candidate (job finished)"
    if upload_id in state.finished:
        if now - state.finished[upload_id] > FINISHED_RETENTION:
            return DELETE, "finished job without a candidate, finished over 7 days ago"
        return KEEP, "finished job without a candidate, finished under 7 days ago"
    if now - file.modified > ORPHAN_RETENTION:
        return DELETE, "in no job, older than 1 day"
    return KEEP, "in no job, younger than 1 day"


def _delete(upload_dir: Path, name: str) -> str:
    """Delete one planned file after checking its path again. Returns "deleted", "gone" or "error"."""
    path = upload_dir / name
    if parse_name(name) is None or path.parent.resolve() != upload_dir.resolve():
        return "error"
    try:
        if path.is_symlink() or not path.is_file():
            return "gone" if not path.exists() else "error"
        path.unlink()
        return "deleted"
    except FileNotFoundError:
        return "gone"
    except OSError:
        return "error"


def run(session: Session, upload_dir: Path, *, delete: bool = False, now: datetime | None = None) -> Report:
    """Plan (and with delete=True, apply) the retention rules. The database is only read."""
    now = now or datetime.now(UTC)
    report = Report(dry_run=not delete)
    files, report.unexpected = list_files(upload_dir)
    state = load_state(session)  # read after listing: a file created meanwhile is simply not in this run
    for file in files:
        report.files[file.kind] += 1
        action, reason = decide(file, state, now)
        if action == KEEP:
            report.kept[reason] += 1
            continue
        report.to_delete[reason] += 1
        if delete:
            outcome = _delete(upload_dir, file.name)
            if outcome == "deleted":
                report.deleted += 1
            elif outcome == "gone":
                report.already_gone += 1
            else:
                report.errors += 1
    return report


def format_report(report: Report) -> list[str]:
    mode = "dry run: nothing is deleted" if report.dry_run else "deleting"
    lines = [f"Upload retention ({mode})",
             f"  {report.files['pdf']} PDFs, {report.files['json']} metadata files, {report.files['part']} interrupted "
             f"copies, {report.unexpected} unexpected entries (never touched)"]
    lines += [f"  keep    {n:4}  {reason}" for reason, n in sorted(report.kept.items())]
    lines += [f"  delete  {n:4}  {reason}" for reason, n in sorted(report.to_delete.items())]
    total = sum(report.to_delete.values())
    if report.dry_run:
        lines.append(f"  {total} files would be deleted. Run again with --delete to delete them.")
    else:
        lines.append(f"  {report.deleted} files deleted, {report.already_gone} already gone, {report.errors} errors.")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.services.upload_retention",
                                     description="Remove uploads that are no longer needed (dry run by default).")
    parser.add_argument("--delete", action="store_true", help="really delete the files (default: only report)")
    args = parser.parse_args(argv)

    from app.config import get_settings
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        report = run(session, get_settings().upload_dir, delete=args.delete)
    for line in format_report(report):
        print(line)
    logger.info("Upload retention: %d to delete, %d deleted, %d errors (dry run: %s)",
                sum(report.to_delete.values()), report.deleted, report.errors, report.dry_run)
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
