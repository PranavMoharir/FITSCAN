"""Background-job state changes, progress, heartbeats and log lines (LLD §5.2, §5.5, §5.6).

Every state change is ONE conditional UPDATE (ADR-006), so two processes can never both win:

    queued  -> running    claim()   only if the job is still queued (not cancelled meanwhile)
    running -> completed  finish()  only if the job is still running
    running -> failed     finish()  only if the job is still running
    running -> cancelled  finish()  only if the job is still running

completed, failed and cancelled are final: no function here changes a job in those states.
The other transitions (queued -> cancelled, queued -> failed, stale-job checks) live in
`app/services/background_jobs.py`, with the same conditional style.
"""

import logging
import uuid
from typing import Any

from sqlalchemy import func, insert, update
from sqlalchemy.orm import Session

from app.models import BackgroundJob, BackgroundJobLog

logger = logging.getLogger(__name__)

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
FINAL_STATUSES = ("completed", "failed", "cancelled")


def claim(session: Session, job_id: uuid.UUID) -> bool:
    """queued -> running. False if the job is not queued (cancelled, already claimed, unknown)."""
    claimed = session.execute(
        update(BackgroundJob)
        .where(BackgroundJob.background_job_id == job_id, BackgroundJob.status == "queued")
        .values(status="running", started_at=func.now(), heartbeat_at=func.now())
        .returning(BackgroundJob.background_job_id)
    ).first()
    return claimed is not None


def record_progress(
    session: Session, job_id: uuid.UUID, *, current: int, total: int | None, succeeded: int, failed: int
) -> bool | None:
    """Save progress and counters and write the heartbeat.

    Returns the job's cancel_requested flag, or None if the job is no longer running
    (for example the stale-job check failed it); the task must then stop.
    """
    row = session.execute(
        update(BackgroundJob)
        .where(BackgroundJob.background_job_id == job_id, BackgroundJob.status == "running")
        .values(progress_current=current, progress_total=total, items_succeeded=succeeded,
                items_failed=failed, heartbeat_at=func.now())
        .returning(BackgroundJob.cancel_requested)
    ).first()
    return None if row is None else row.cancel_requested


def heartbeat(session: Session, job_id: uuid.UUID) -> bool:
    """Write the heartbeat only. False if the job is no longer running."""
    row = session.execute(
        update(BackgroundJob)
        .where(BackgroundJob.background_job_id == job_id, BackgroundJob.status == "running")
        .values(heartbeat_at=func.now())
        .returning(BackgroundJob.background_job_id)
    ).first()
    return row is not None


def finish(
    session: Session, job_id: uuid.UUID, status: str, *, error_message: str | None = None, progress_total: int | None = None
) -> bool:
    """running -> completed / failed / cancelled. False if the job was not running."""
    if status not in FINAL_STATUSES:
        raise ValueError(f"{status!r} is not a final status")
    values: dict[str, Any] = {"status": status, "finished_at": func.now(), "heartbeat_at": func.now()}
    if error_message is not None:
        values["error_message"] = error_message
    if progress_total is not None:
        values["progress_total"] = progress_total
    row = session.execute(
        update(BackgroundJob)
        .where(BackgroundJob.background_job_id == job_id, BackgroundJob.status == "running")
        .values(**values)
        .returning(BackgroundJob.background_job_id)
    ).first()
    return row is not None


def add_log(session: Session, job_id: uuid.UUID, level: str, message: str, **context: Any) -> None:
    """Append a timestamped log line. Logs hold URLs, file names and reasons, never personal data."""
    if level not in LOG_LEVELS:
        raise ValueError(f"unknown log level {level!r}")
    context = {key: value for key, value in context.items() if value is not None}
    session.execute(
        insert(BackgroundJobLog).values(
            background_job_id=job_id, level=level, message=message[:2000], context=context or None
        )
    )
    logger.log(logging.getLevelName(level), "[%s] %s", job_id, message)
