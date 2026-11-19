"""The Celery application (LLD §5.1). `app/worker/` is the only package that imports Celery.

Start a worker from the `backend/` folder:

    celery -A app.worker.celery_app worker --loglevel=INFO
    (on Windows, add --pool=solo)

Redis is only the message broker. Task status, progress, logs and results are stored in
PostgreSQL (ADR-003), so no Celery result backend is configured.
Tasks live in `app/worker/tasks.py` (crawl and resume so far; match in a later phase).
"""

import logging

from celery import Celery
from celery.signals import worker_process_init, worker_ready

from app.config import get_settings

logger = logging.getLogger(__name__)

celery_app = Celery("fitscan", broker=get_settings().redis_url, include=["app.worker.tasks"])

celery_app.conf.update(
    # A long task must not reserve queued tasks that another free worker could run (LLD §5.1).
    worker_prefetch_multiplier=1,
    # Messages carry only a background_job_id (ADR-004), so plain JSON is enough.
    task_serializer="json",
    accept_content=["json"],
    # Results live in PostgreSQL, not in Celery (ADR-003).
    task_ignore_result=True,
    # Keep retrying the broker connection when the worker starts before Redis is ready.
    broker_connection_retry_on_startup=True,
    # Fail fast when the API publishes a task and Redis is down (it then answers 503).
    broker_connection_timeout=3,
    timezone="UTC",
    enable_utc=True,
)


@worker_process_init.connect
def _fresh_database_connections(**_) -> None:
    """Each forked worker process opens its own database connections (never share a socket)."""
    from app.db.session import engine

    engine.dispose(close=False)


@worker_ready.connect
def _on_worker_ready(**_) -> None:
    """At start-up: fail stale jobs (LLD §5.8) and sync the skills table from the taxonomy (LLD §6.8)."""
    from app.db.session import session_scope
    from app.services.background_jobs import fail_stale_jobs
    from app.skills.sync import sync_skills

    try:
        with session_scope() as session:
            running, queued = fail_stale_jobs(session)
            count = sync_skills(session)
        logger.info("Worker ready: %d skills synced; stale jobs failed: %d running, %d queued", count, running, queued)
    except Exception:
        logger.exception("Start-up checks failed; the worker keeps running and retries them on the next start")
