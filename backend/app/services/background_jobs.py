"""Background-job control for the API: create, list, read, logs, cancel, stale-job checks (LLD §5.4-5.8).

Creating a job (crawl, resume or match): insert the row as `queued` and COMMIT first (so the worker can
always find it), then publish a Celery message that carries only the job ID (ADR-004). If
publishing fails, the job is marked `failed` ("could not be queued") and the API answers 503.
"""

import logging
import uuid
from dataclasses import asdict
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, aliased

from app.config import check_weight_values, get_settings
from app.crawler.ssrf import BlockedHostError, UnresolvableHostError, check_host
from app.crawler.urls import host_of, is_allowed_host, normalize_url
from app.errors import AppError
from app.extractors.registry import get_registry
from app.models import BackgroundJob, BackgroundJobLog, Candidate
from app.resumes.validation import AcceptedFile, IncomingFile, RejectedFile, delete_stored, save_upload, stored_name
from app.schemas.background_job import CrawlRequest
from app.worker.celery_app import celery_app
from app.worker.progress import LOG_LEVELS, add_log

logger = logging.getLogger(__name__)

MAX_LOG_LINES = 500  # per request; the client asks again with next_after_id


def _not_found() -> AppError:
    return AppError(404, "NOT_FOUND", "Background job not found.")


def _invalid(field: str, message: str) -> AppError:
    """Same shape as FastAPI's own validation errors (app/errors.py)."""
    return AppError(422, "VALIDATION_ERROR", "The request is not valid.", {"errors": [{"field": field, "message": message}]})


# --- Celery messages (tests replace these two functions) -------------------------------------------


def publish_task(task_name: str, job_id: uuid.UUID) -> str:
    """Send the task with only the job ID. Raises if Redis cannot be reached."""
    result = celery_app.send_task(
        task_name, args=[str(job_id)], retry=True,
        retry_policy={"max_retries": 2, "interval_start": 0, "interval_step": 0.5, "interval_max": 1},
    )
    return result.id


def revoke_task(task_id: str) -> None:
    """Best effort: ask Celery to drop a task that is still queued (the claim check is the real guard)."""
    try:
        celery_app.control.revoke(task_id)
    except Exception as exc:
        logger.warning("Could not revoke task %s: %s", task_id, type(exc).__name__)


# --- Create ------------------------------------------------------------------------------------------


def validate_crawl_request(request: CrawlRequest) -> dict:
    """The checks that need runtime information (LLD §5.9). Returns the job's params."""
    settings = get_settings()
    seed = normalize_url(str(request.seed_url))
    if seed is None:
        raise _invalid("body.seed_url", "must be an http or https URL")
    seed_host = host_of(seed)
    allowed = request.allowed_domains or [seed_host]
    if not is_allowed_host(seed_host, allowed):
        raise _invalid("body.seed_url", "the seed URL's host is not in allowed_domains")
    try:
        check_host(seed_host, settings.crawler_private_host_allowlist)
    except BlockedHostError:
        raise _invalid("body.seed_url", "the seed URL resolves to a private or reserved address") from None
    except UnresolvableHostError:
        raise _invalid("body.seed_url", "the seed URL's host name does not resolve") from None
    registry = get_registry()
    if request.extractor is not None and request.extractor not in registry.names:
        raise _invalid("body.extractor", f"unknown extractor; choose one of {registry.names}")
    if request.extractor is not None and not registry.get(request.extractor).demo:
        # A demo site's invented jobs must stay labelled demo (the crawler drops them anyway).
        demo = registry.demo_site(seed) or next(
            (site for site in (registry.demo_site(f"https://{host}/") for host in allowed) if site), None)
        if demo is not None:
            raise _invalid("body.extractor", f"this crawl reaches a demo site, whose jobs are taken only by the "
                                             f"{demo.name} extractor; leave the extractor empty")
    return {"seed_url": seed, "max_depth": request.max_depth, "max_pages": request.max_pages,
            "allowed_domains": allowed, "extractor": request.extractor}


def _enqueue(session: Session, job: BackgroundJob) -> BackgroundJob:
    """Insert the queued job and COMMIT, then publish its task (LLD §5.4). Broker down: failed + 503."""
    session.add(job)
    session.commit()  # commit first, so the worker can always find the row
    session.refresh(job)

    try:
        task_id = publish_task(job.type, job.background_job_id)
    except Exception as exc:
        logger.error("Could not publish %s task for %s: %s", job.type, job.background_job_id, type(exc).__name__)
        session.execute(
            update(BackgroundJob)
            .where(BackgroundJob.background_job_id == job.background_job_id, BackgroundJob.status == "queued")
            .values(status="failed", finished_at=func.now(),
                    error_message="The job could not be queued: the message broker is unavailable.")
        )
        add_log(session, job.background_job_id, "ERROR", "Could not be queued: the message broker is unavailable.")
        session.commit()
        raise AppError(503, "SERVICE_UNAVAILABLE", "Service temporarily unavailable.", {"broker": "down"}) from None

    session.execute(update(BackgroundJob).where(BackgroundJob.background_job_id == job.background_job_id)
                    .values(celery_task_id=task_id))
    session.commit()
    return job


def create_crawl_job(session: Session, request: CrawlRequest) -> BackgroundJob:
    params = validate_crawl_request(request)
    return _enqueue(session, BackgroundJob(type="crawl", status="queued", params=params,
                                           progress_total=request.max_pages))


def create_resume_job(session: Session, files: list[IncomingFile]) -> tuple[BackgroundJob, list[AcceptedFile],
                                                                                   list[RejectedFile]]:
    """Check and store each uploaded file, then queue one `resume` job for the accepted ones (LLD §6.2).

    A rejected file does not stop the others. With no accepted file, nothing is stored and no job
    is created: 422 NO_VALID_FILES with every file's reason. Files are identified by their position
    in the request (`index`), never by name. The job's params list the stored files by upload ID
    and generated storage name only; the original names wait in each upload's metadata file for
    the worker.
    """
    settings = get_settings()
    if not files:
        raise _invalid("body.files", "at least one file is required")
    if len(files) > settings.max_upload_files:
        raise _invalid("body.files", f"at most {settings.max_upload_files} files per request (MAX_UPLOAD_FILES)")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    accepted: list[AcceptedFile] = []
    rejected: list[RejectedFile] = []
    try:
        for index, incoming in enumerate(files):
            result = save_upload(incoming.stream, incoming.filename, incoming.content_type, settings.upload_dir,
                                 max_bytes, index=index)
            (accepted if isinstance(result, AcceptedFile) else rejected).append(result)
        if not accepted:
            raise AppError(422, "NO_VALID_FILES", "No file was accepted, so no job was created.",
                           {"rejected_files": [asdict(item) for item in rejected]})  # index, code, message
        params = {"files": [{"upload_id": a.upload_id, "stored_file": stored_name(a.upload_id),
                             "size_bytes": a.size_bytes} for a in accepted]}
        job = _enqueue(session, BackgroundJob(type="resume", status="queued", params=params,
                                              progress_total=len(accepted)))
    except BaseException:
        delete_stored(settings.upload_dir, accepted)  # no job will process them (e.g. broker down: 503)
        raise
    logger.info("Resume job %s queued: %d files accepted, %d rejected", job.background_job_id, len(accepted), len(rejected))
    return job, accepted, rejected


# --- Match weights (LLD §7.4) --------------------------------------------------------------------------
#
# Every match run records the weights it uses in params["weights"]. Runs from before weights were
# recorded have params = None: their weights are "not recorded" (their stored points and
# explanations still say exactly what each match received).

WEIGHT_KEYS = ("required", "nice", "experience", "location")
MATCH_QUEUE_LOCK = 7202611  # pg_advisory_xact_lock key: one transaction at a time creates a match run


def _number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


def default_weights() -> dict:
    """MATCH_WEIGHTS (70, 15, 10, 5 unless configured otherwise), as JSON numbers."""
    weights = get_settings().match_weights
    return {key: _number(getattr(weights, key)) for key in WEIGHT_KEYS}


def recorded_weights(params: object) -> dict | None:
    """A run's recorded weights, or None if it has none (an older run) or they are not valid."""
    weights = params.get("weights") if isinstance(params, dict) else None
    if not isinstance(weights, dict) or set(weights) != set(WEIGHT_KEYS):
        return None
    values = [weights[key] for key in WEIGHT_KEYS]
    if any(isinstance(value, bool) or not isinstance(value, int | float) for value in values):
        return None
    try:
        check_weight_values(values)
    except ValueError:
        return None
    return {key: weights[key] for key in WEIGHT_KEYS}


def active_weights(session: Session) -> tuple[dict, uuid.UUID | None]:
    """The weights a match run uses when none are given, and the run they come from (None: MATCH_WEIGHTS).

    They are the weights of the most recently created match run that is queued, running or
    completed and has recorded weights. A run that is queued or running counts, so the latest
    choice is kept while it runs. Failed and cancelled runs (superseded ones included) never
    change them. With no such run, they are MATCH_WEIGHTS.
    """
    rows = session.execute(
        select(BackgroundJob.background_job_id, BackgroundJob.params)
        .where(BackgroundJob.type == "match", BackgroundJob.status.in_(("queued", "running", "completed")),
               BackgroundJob.params.has_key("weights"))
        .order_by(BackgroundJob.created_at.desc(), BackgroundJob.background_job_id.desc())
        .limit(20)  # only a hand-edited row could hold invalid weights; those are skipped
    ).all()
    for job_id, params in rows:
        weights = recorded_weights(params)
        if weights is not None:
            return weights, job_id
    return default_weights(), None


def results_weights(session: Session) -> dict | None:
    """The run whose results are stored (the completed match run that started last, LLD §7.9) and its
    weights (None: not recorded). None if no match run has completed yet."""
    row = session.execute(
        select(BackgroundJob.background_job_id, BackgroundJob.params)
        .where(BackgroundJob.type == "match", BackgroundJob.status == "completed")
        .order_by(BackgroundJob.started_at.desc(), BackgroundJob.background_job_id.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return {"background_job_id": row.background_job_id, "weights": recorded_weights(row.params)}


def create_match_job(session: Session, weights: dict | None = None) -> BackgroundJob:
    """Queue a run that scores every candidate against every job (LLD §7.1) with `weights` (already
    validated), or with the active weights when none are given. The resolved weights are stored in
    the job's params, so every new run records what it used.

    progress_total starts as today's number of candidates; the worker sets it again when it
    loads them. With no candidates or no jobs the job is still created and fails with that reason.
    """
    session.execute(select(func.pg_advisory_xact_lock(MATCH_QUEUE_LOCK)))  # released when _enqueue commits
    if weights is None:
        weights, _ = active_weights(session)
    candidates = session.execute(select(func.count()).select_from(Candidate)).scalar_one()
    return _enqueue(session, BackgroundJob(type="match", status="queued", params={"weights": weights},
                                           progress_total=candidates))


def request_auto_match(session: Session, crawl_job_id: uuid.UUID) -> tuple[str, uuid.UUID | None]:
    """Queue a match run after a crawl that saved new or changed jobs (LLD §7.1). `session` must be fresh.

    Under the same lock as create_match_job, so manual and automatic requests are decided one at
    a time. Returns (outcome, match run ID):
      "already_requested": a match run was already queued for this crawl;
      "already_queued": a match run is queued; it loads all jobs when it starts, these included;
      "no_candidates": nothing to match yet;
      "queued": a new run with the active weights, and params.after_crawl = the crawl.
    A run that is already *running* does not count: it may have loaded the jobs before this crawl
    saved them. Raises AppError (503) if the broker is down; the new run is then marked failed.
    """
    session.execute(select(func.pg_advisory_xact_lock(MATCH_QUEUE_LOCK)))  # the first statement of the transaction
    match_runs = select(BackgroundJob.background_job_id).where(BackgroundJob.type == "match")
    earlier = session.execute(match_runs.where(BackgroundJob.params["after_crawl"].astext == str(crawl_job_id))
                              .limit(1)).scalar_one_or_none()
    if earlier is not None:
        session.rollback()  # ends the transaction: releases the lock
        return "already_requested", earlier
    queued = session.execute(match_runs.where(BackgroundJob.status == "queued")
                             .order_by(BackgroundJob.created_at.desc()).limit(1)).scalar_one_or_none()
    if queued is not None:
        session.rollback()
        return "already_queued", queued
    candidates = session.execute(select(func.count()).select_from(Candidate)).scalar_one()
    if candidates == 0:
        session.rollback()
        return "no_candidates", None
    weights, _ = active_weights(session)
    job = _enqueue(session, BackgroundJob(type="match", status="queued", progress_total=candidates,
                                          params={"weights": weights, "after_crawl": str(crawl_job_id)}))
    return "queued", job.background_job_id


# --- Read --------------------------------------------------------------------------------------------


def list_jobs(session: Session, *, job_type: str | None, status: str | None, page: int, page_size: int):
    """Newest first. Runs the stale-job check first, as LLD §5.8 requires."""
    fail_stale_jobs(session)
    query = select(BackgroundJob)
    if job_type:
        query = query.where(BackgroundJob.type == job_type)
    if status:
        query = query.where(BackgroundJob.status == status)
    total = session.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    items = session.execute(
        query.order_by(BackgroundJob.created_at.desc(), BackgroundJob.background_job_id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return items, total


def get_job(session: Session, job_id: uuid.UUID) -> BackgroundJob:
    job = session.get(BackgroundJob, job_id)
    if job is None:
        raise _not_found()
    return job


def get_logs(session: Session, job_id: uuid.UUID, *, after_id: int, min_level: str | None, limit: int = MAX_LOG_LINES):
    """Log lines oldest first, only those after `after_id`; `min_level` keeps that level and above."""
    get_job(session, job_id)
    query = select(BackgroundJobLog).where(BackgroundJobLog.background_job_id == job_id, BackgroundJobLog.log_id > after_id)
    if min_level:
        query = query.where(BackgroundJobLog.level.in_(LOG_LEVELS[LOG_LEVELS.index(min_level):]))
    items = session.execute(query.order_by(BackgroundJobLog.log_id).limit(limit)).scalars().all()
    next_after_id = items[-1].log_id if items else after_id
    return items, next_after_id


# --- Cancel (LLD §5.7) -------------------------------------------------------------------------------


def cancel_job(session: Session, job_id: uuid.UUID) -> tuple[int, dict]:
    """(HTTP status, body): 200 queued job cancelled, 202 running job asked to stop, 409 already finished."""
    job = get_job(session, job_id)

    cancelled = session.execute(
        update(BackgroundJob)
        .where(BackgroundJob.background_job_id == job_id, BackgroundJob.status == "queued")
        .values(status="cancelled", finished_at=func.now())
        .returning(BackgroundJob.celery_task_id)
    ).first()
    if cancelled is not None:
        add_log(session, job_id, "INFO", "Cancelled by user before it started.")
        session.commit()
        if cancelled.celery_task_id:
            revoke_task(cancelled.celery_task_id)
        return 200, {"status": "cancelled"}

    requested = session.execute(
        update(BackgroundJob)
        .where(BackgroundJob.background_job_id == job_id, BackgroundJob.status == "running")
        .values(cancel_requested=True)
        .returning(BackgroundJob.background_job_id)
    ).first()
    if requested is not None:
        add_log(session, job_id, "INFO", "Cancellation requested; the worker stops after the current item.")
        session.commit()
        return 202, {"status": "running", "cancel_requested": True}

    session.rollback()
    session.refresh(job)
    raise AppError(409, "CONFLICT", f"The background job is already {job.status}.")


# --- Stale-job checks (LLD §5.8, decisions LLD-7 and LLD-8) -----------------------------------------


def _duration(seconds: int) -> str:
    if seconds % 60 == 0:
        minutes = seconds // 60
        return f"{minutes} minute" + ("s" if minutes != 1 else "")
    return f"{seconds} seconds"


def fail_stale_jobs(session: Session) -> tuple[int, int]:
    """Fail running jobs without a recent heartbeat, and queued jobs that no worker picked up.

    Safe to run at any time and from several places: each UPDATE changes only rows that still
    match its conditions. Lost tasks are not re-sent; the user starts the job again.
    Returns (running jobs failed, queued jobs failed).
    """
    settings = get_settings()
    heartbeat_timeout = settings.job_heartbeat_timeout_seconds
    queued_timeout = settings.job_queued_timeout_seconds

    lost_worker_message = "Worker stopped unexpectedly."
    lost = session.execute(
        update(BackgroundJob)
        .where(BackgroundJob.status == "running",
               BackgroundJob.heartbeat_at < func.now() - timedelta(seconds=heartbeat_timeout))
        .values(status="failed", finished_at=func.now(), error_message=lost_worker_message)
        .returning(BackgroundJob.background_job_id)
    ).scalars().all()

    # "No job has written a heartbeat during that period" looks at ALL jobs, so the subquery
    # uses an alias; without it, it would only look at the row being updated.
    never_picked_message = (f"No worker picked up this job within {_duration(queued_timeout)}. "
                            "The worker may be stopped, or the task was lost. Start it again.")
    other = aliased(BackgroundJob, name="other_job")
    recent_heartbeat = (select(other.background_job_id)
                        .where(other.heartbeat_at > func.now() - timedelta(seconds=queued_timeout))
                        .exists())
    never_picked = session.execute(
        update(BackgroundJob)
        .where(BackgroundJob.status == "queued",
               BackgroundJob.created_at < func.now() - timedelta(seconds=queued_timeout),
               ~recent_heartbeat)
        .values(status="failed", finished_at=func.now(), error_message=never_picked_message)
        .returning(BackgroundJob.background_job_id)
    ).scalars().all()

    for job_id in lost:
        add_log(session, job_id, "ERROR", lost_worker_message)
    for job_id in never_picked:
        add_log(session, job_id, "ERROR", never_picked_message)
    session.commit()
    if lost or never_picked:
        logger.warning("Stale-job check failed %d running and %d queued jobs", len(lost), len(never_picked))
    return len(lost), len(never_picked)
