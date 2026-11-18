"""Celery task entry points (LLD §5.5). Tasks are thin: claim the job, call the domain code, finish.

Only `crawl` exists so far; `resume` and `match` are added in later phases.
"""

import logging
import uuid

from celery.exceptions import SoftTimeLimitExceeded

from app.config import Settings, get_settings
from app.crawler import browser, fetcher as fetcher_module
from app.crawler.fetcher import Fetcher
from app.crawler.frontier import Crawler, CrawlSettings, CrawlStats, SeedRejectedError
from app.crawler.pipeline import BuiltRecord, SaveResult, save_records
from app.crawler.rate_limiter import RateLimiter
from app.db.session import session_scope
from app.extractors.registry import get_registry
from app.models import BackgroundJob
from app.worker import progress
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

CRAWL_SOFT_TIME_LIMIT_SECONDS = 3600  # a hung crawl is stopped after an hour; partial results are kept


class JobRun:
    """The CrawlSink for one background job: every report is a short PostgreSQL transaction."""

    def __init__(self, job_id: uuid.UUID, total: int | None):
        self.job_id = job_id
        self.total = total         # progress_total while running: max_pages
        self.cancel_seen = False   # the user asked to stop
        self.not_running = False   # someone else ended the job (e.g. the stale-job check)

    def log(self, level: str, message: str, **context) -> None:
        with session_scope() as session:
            progress.add_log(session, self.job_id, level, message, **context)

    def save(self, records: list[BuiltRecord]) -> SaveResult:
        with session_scope() as session:
            return save_records(session, records, self.job_id)

    def page_done(self, stats: CrawlStats) -> bool:
        """Progress + heartbeat after every page; True tells the crawler to stop."""
        with session_scope() as session:
            cancel = progress.record_progress(
                session, self.job_id, current=stats.pages_processed, total=self.total,
                succeeded=stats.pages_succeeded, failed=stats.pages_failed,
            )
        if cancel is None:
            self.not_running = True
            return True
        if cancel:
            self.cancel_seen = True
            return True
        return False

    def finish(self, status: str, error_message: str | None = None, progress_total: int | None = None) -> bool:
        with session_scope() as session:
            return progress.finish(session, self.job_id, status, error_message=error_message, progress_total=progress_total)


def build_crawler(params: dict, sink: JobRun, settings: Settings) -> Crawler:
    """Wire the crawler from configuration. Tests replace fetcher.create_client and browser.BrowserRenderer."""
    rate_limiter = RateLimiter(settings.crawler_default_delay_seconds)
    fetcher = Fetcher(
        fetcher_module.create_client(settings.crawler_request_timeout_seconds),
        user_agent=settings.crawler_user_agent,
        max_retries=settings.crawler_max_retries,
        allowed_domains=params["allowed_domains"],
        private_allowlist=settings.crawler_private_host_allowlist,
        rate_limiter=rate_limiter,
        log=sink.log,
    )
    crawl_settings = CrawlSettings(
        seed_url=params["seed_url"], max_depth=params["max_depth"], max_pages=params["max_pages"],
        allowed_domains=params["allowed_domains"], extractor=params.get("extractor"),
    )

    def make_renderer():
        return browser.BrowserRenderer(
            allowed_domains=params["allowed_domains"],
            private_allowlist=settings.crawler_private_host_allowlist,
            timeout_seconds=settings.crawler_request_timeout_seconds,
            user_agent=settings.crawler_user_agent,
        )

    return Crawler(crawl_settings, fetcher, get_registry(), sink, make_renderer)


def run_crawl_job(job_id: uuid.UUID) -> str:
    """Run one crawl job to its final state. Returns the final status ("not-claimed" if not queued)."""
    with session_scope() as session:
        if not progress.claim(session, job_id):
            logger.info("Crawl %s is not queued (cancelled, unknown or already taken); nothing to do", job_id)
            return "not-claimed"
        params = dict(session.get(BackgroundJob, job_id).params or {})

    run = JobRun(job_id, total=params.get("max_pages"))
    try:
        run.log("INFO", f"Crawl started: {params['seed_url']} (max_depth {params['max_depth']}, "
                        f"max_pages {params['max_pages']}, allowed domains {', '.join(params['allowed_domains'])})")
        stats = build_crawler(params, run, get_settings()).run()
    except SoftTimeLimitExceeded:
        run.log("ERROR", "Time limit exceeded; the crawl was stopped. Jobs saved so far are kept.")
        run.finish("failed", "Time limit exceeded.")
        return "failed"
    except SeedRejectedError as exc:
        run.log("ERROR", str(exc))
        run.finish("failed", str(exc))
        return "failed"
    except Exception as exc:  # outside the per-page boundary, e.g. the database went away
        logger.exception("Crawl %s failed", job_id)
        message = f"Unexpected error during the crawl ({type(exc).__name__}). Jobs saved so far are kept."
        try:
            run.log("ERROR", message)
            run.finish("failed", message)
        except Exception:
            logger.exception("Could not record the failure of %s; the stale-job check will mark it", job_id)
        return "failed"

    if run.not_running:
        logger.warning("Crawl %s was ended elsewhere while running; its state is left unchanged", job_id)
        return "not-running"
    if run.cancel_seen:
        run.log("INFO", f"Cancelled by user after {stats.pages_processed} items.")
        run.finish("cancelled")
        return "cancelled"
    if stats.pages_succeeded > 0:
        # The crawl may run out of pages before max_pages: show 100 % at the end (LLD §5.6).
        run.finish("completed", progress_total=stats.pages_processed)
        return "completed"
    if stats.pages_failed > 0:
        message = f"All {stats.pages_failed} pages failed."
    else:
        message = "No page could be crawled: every URL was skipped (see the log)."
    run.log("ERROR", message)
    run.finish("failed", message)
    return "failed"


@celery_app.task(name="crawl", soft_time_limit=CRAWL_SOFT_TIME_LIMIT_SECONDS, time_limit=CRAWL_SOFT_TIME_LIMIT_SECONDS + 60)
def crawl(background_job_id: str) -> str:
    """The message carries only the job ID (ADR-004); everything else is read from PostgreSQL."""
    return run_crawl_job(uuid.UUID(background_job_id))
