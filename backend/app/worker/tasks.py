"""Celery task entry points (LLD §5.5). Tasks are thin: claim the job, call the domain code, finish.

Three tasks: `crawl`, `resume` and `match`.
"""

import logging
import os
import traceback
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date

from celery.exceptions import SoftTimeLimitExceeded

from app.config import Settings, get_settings
from app.crawler import browser, fetcher as fetcher_module
from app.crawler.fetcher import Fetcher
from app.crawler.frontier import Crawler, CrawlSettings, CrawlStats, SeedRejectedError
from app.crawler.pipeline import BuiltRecord, SaveResult, save_records
from app.crawler.rate_limiter import RateLimiter
from app.db.session import session_scope
from app.extractors.registry import get_registry
from app.matching.engine import MatchRow, load_inputs, save_matches, score_candidate
from app.matching.explanation import display
from app.matching.scoring import Weights
from app.matching.tfidf import TextSimilarity
from app.models import BackgroundJob
from app.resumes.pipeline import FileFailed, file_sha256, find_by_file, parse_resume, save_candidate
from app.resumes.validation import read_source_file, stored_name
from app.worker import progress
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

CRAWL_SOFT_TIME_LIMIT_SECONDS = 3600  # a hung crawl is stopped after an hour; partial results are kept
RESUME_SOFT_TIME_LIMIT_SECONDS = 3600  # the same for a resume job; saved candidates are kept
MATCH_SOFT_TIME_LIMIT_SECONDS = 3600  # a match run that is stopped saves nothing: the previous matches stay


class JobRun:
    """Reports of one running background job: every report is a short PostgreSQL transaction.

    It is also the crawler's CrawlSink (`save`, `page_done`).
    """

    def __init__(self, job_id: uuid.UUID, total: int | None):
        self.job_id = job_id
        self.total = total         # progress_total while running: max_pages, or the number of files
        self.cancel_seen = False   # the user asked to stop
        self.not_running = False   # someone else ended the job (e.g. the stale-job check)

    def log(self, level: str, message: str, **context) -> None:
        with session_scope() as session:
            progress.add_log(session, self.job_id, level, message, **context)

    def item_done(self, current: int, succeeded: int, failed: int) -> bool:
        """Progress, counters and heartbeat after every item; True means "stop now"."""
        with session_scope() as session:
            cancel = progress.record_progress(
                session, self.job_id, current=current, total=self.total, succeeded=succeeded, failed=failed,
            )
        if cancel is None:
            self.not_running = True
            return True
        if cancel:
            self.cancel_seen = True
            return True
        return False

    def heartbeat(self) -> None:
        """Within a long item (e.g. OCR of many pages), so the stale-job check sees the worker alive."""
        with session_scope() as session:
            if not progress.heartbeat(session, self.job_id):
                self.not_running = True

    def save(self, records: list[BuiltRecord]) -> SaveResult:
        with session_scope() as session:
            return save_records(session, records, self.job_id)

    def page_done(self, stats: CrawlStats) -> bool:
        """Progress + heartbeat after every page; True tells the crawler to stop."""
        return self.item_done(stats.pages_processed, stats.pages_succeeded, stats.pages_failed)

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


# --- Resume parsing (LLD Part 6) --------------------------------------------------------------------
#
# Privacy: log lines identify a file by its upload ID, never by its original name, and never
# contain resume text, names or contact details. Exception messages are not logged either (a
# database error can quote the values it rejected): only the exception type and the code location.


def current_date() -> date:
    """The date "Present" stands for in employment ranges (tests replace this function)."""
    return date.today()


def safe_traceback(exc: BaseException) -> str:
    """Exception type and code locations only: no message, because messages can quote data."""
    frames = "".join(traceback.format_tb(exc.__traceback__))
    return f"{type(exc).__name__} (message withheld)\n{frames}"


@dataclass
class ResumeCounts:
    created: int = 0
    updated: int = 0
    duplicates: int = 0
    failed: int = 0

    @property
    def succeeded(self) -> int:
        return self.created + self.updated

    @property
    def processed(self) -> int:
        return self.succeeded + self.duplicates + self.failed


def process_resume_file(run: JobRun, item: dict, settings: Settings, today: date,
                        counts: ResumeCounts, unmatched: Counter) -> None:
    """One file: duplicate check, parse, validate, save. Every outcome is counted and logged."""
    upload_id = item["upload_id"]
    prefix = f"Resume upload {upload_id[:8]}"
    try:
        name = stored_name(upload_id)  # built from the UUID, never taken from the request
        path = settings.upload_dir / name
        if not path.is_file():
            raise FileFailed("the stored file is missing from the uploads volume.")
        source_file = read_source_file(settings.upload_dir, upload_id)
        if source_file is None:
            source_file = "unnamed.pdf"
            run.log("WARNING", f"{prefix}: the original file name is not available; 'unnamed.pdf' is used.",
                    upload_id=upload_id)
        sha256 = file_sha256(path)
        with session_scope() as session:
            duplicate_of = find_by_file(session, sha256)
        if duplicate_of is not None:
            counts.duplicates += 1
            run.log("INFO", f"{prefix}: duplicate file, skipped (an existing candidate has the same file).",
                    upload_id=upload_id, candidate_id=str(duplicate_of))
            return

        parsed = parse_resume(path, source_file=source_file, sha256=sha256, stored_path=name, settings=settings,
                              today=today, on_page=lambda _page: run.heartbeat())
        for event in parsed.events:
            run.log(event.level, f"{prefix}: {event.message}", upload_id=upload_id, page=event.page)
        with session_scope() as session:
            outcome = save_candidate(session, parsed.record, run.job_id)

        if outcome.action == "duplicate":
            counts.duplicates += 1
            run.log("INFO", f"{prefix}: duplicate file, skipped (an existing candidate has the same file).",
                    upload_id=upload_id, candidate_id=str(outcome.candidate_id))
            return
        if outcome.action == "created":
            counts.created += 1
            action = "created a new candidate"
        else:
            counts.updated += 1
            action = "updated the existing candidate with the same email"
        ocr_note = f", OCR on page {', '.join(map(str, parsed.ocr_pages))}" if parsed.ocr_pages else ""
        record = parsed.record
        run.log("INFO", f"{prefix}: parsed ({action}{ocr_note}).", upload_id=upload_id,
                candidate_id=str(outcome.candidate_id), pages=parsed.pages, skills=len(record.skills),
                warnings=len(record.parse_warnings), parsed_with_ocr=record.parsed_with_ocr)
        unmatched.update(parsed.unmatched_terms)
    except FileFailed as exc:
        counts.failed += 1
        for event in exc.events:
            run.log(event.level, f"{prefix}: {event.message}", upload_id=upload_id, page=event.page)
        run.log(exc.level, f"{prefix} failed: {exc.message}", upload_id=upload_id)
    except SoftTimeLimitExceeded:
        raise
    except Exception as exc:  # one bad file never stops the others (LLD §5.5)
        counts.failed += 1
        logger.error("Resume upload %s failed: %s", upload_id, safe_traceback(exc))
        run.log("ERROR", f"{prefix} failed: unexpected error ({type(exc).__name__}).", upload_id=upload_id)


def _finish_resume_job(run: JobRun, counts: ResumeCounts) -> str:
    if run.not_running:
        logger.warning("Resume job %s was ended elsewhere while running; its state is left unchanged", run.job_id)
        return "not-running"
    if run.cancel_seen:
        run.log("INFO", f"Cancelled by user after {counts.processed} items.")
        run.finish("cancelled")
        return "cancelled"
    if counts.succeeded > 0:
        run.finish("completed")
        return "completed"
    if counts.duplicates == 0:
        message = f"All {counts.failed} files failed."
    elif counts.failed == 0:
        message = "No candidate was saved: every file was a duplicate of an existing candidate."
    else:
        message = f"No candidate was saved: {counts.failed} files failed and {counts.duplicates} were duplicates."
    run.log("ERROR", message)
    run.finish("failed", message)
    return "failed"


def run_resume_job(job_id: uuid.UUID) -> str:
    """Parse every file of one resume job, one by one. Returns the final status ("not-claimed" if not queued)."""
    with session_scope() as session:
        if not progress.claim(session, job_id):
            logger.info("Resume job %s is not queued (cancelled, unknown or already taken); nothing to do", job_id)
            return "not-claimed"
        files = list((session.get(BackgroundJob, job_id).params or {}).get("files", []))

    settings = get_settings()
    today = current_date()
    run = JobRun(job_id, total=len(files))
    counts = ResumeCounts()
    unmatched: Counter = Counter()
    try:
        if not settings.upload_dir.is_dir() or not os.access(settings.upload_dir, os.R_OK):
            message = "The uploads volume is not readable, so no file could be processed."
            run.log("ERROR", message)
            run.finish("failed", message)
            return "failed"
        run.log("INFO", f"Resume parsing started: {len(files)} file{'s' if len(files) != 1 else ''}.")
        for index, item in enumerate(files, start=1):
            process_resume_file(run, item, settings, today, counts, unmatched)
            if run.item_done(index, counts.succeeded, counts.failed) or run.not_running:
                break
        run.log("INFO", f"Resume parsing finished: {counts.processed} of {len(files)} files processed "
                        f"({counts.created} new candidates, {counts.updated} updated, "
                        f"{counts.duplicates} duplicates skipped, {counts.failed} failed).")
        if unmatched:
            top = ", ".join(f"{term} ({count})" for term, count in unmatched.most_common(10))
            run.log("INFO", f"Skill-like terms not in the taxonomy: {top}")
    except SoftTimeLimitExceeded:
        run.log("ERROR", "Time limit exceeded; the job was stopped. Candidates saved so far are kept.")
        run.finish("failed", "Time limit exceeded.")
        return "failed"
    except Exception as exc:  # outside the per-file boundary, e.g. the database went away
        logger.error("Resume job %s failed: %s", job_id, safe_traceback(exc))
        message = f"Unexpected error in the resume job ({type(exc).__name__}). Candidates saved so far are kept."
        try:
            run.log("ERROR", message)
            run.finish("failed", message)
        except Exception:
            logger.error("Could not record the failure of %s; the stale-job check will mark it", job_id)
        return "failed"
    return _finish_resume_job(run, counts)


@celery_app.task(name="resume", soft_time_limit=RESUME_SOFT_TIME_LIMIT_SECONDS, time_limit=RESUME_SOFT_TIME_LIMIT_SECONDS + 60)
def resume(background_job_id: str) -> str:
    """The message carries only the job ID (ADR-004): file names and paths are read from PostgreSQL."""
    return run_resume_job(uuid.UUID(background_job_id))


# --- Matching (LLD Part 7) -------------------------------------------------------------------------
#
# One item = one candidate scored against every job. Nothing is written to `matches` until all
# candidates are scored; then all rows are replaced in one transaction. A cancelled, failed or
# stopped run therefore leaves the previous results exactly as they were (LLD §5.7, §7.9).
# Log lines name candidates by the first 8 characters of their ID, never by name.


def _plural(count: int, word: str, plural: str | None = None) -> str:
    return f"{count} {word if count == 1 else plural or word + 's'}"


def score_all(run: JobRun, jobs, candidates, weights: Weights) -> tuple[list[MatchRow], int, int]:
    """Score every candidate against every job. Returns (rows, candidates succeeded, candidates failed)."""
    similarity = TextSimilarity([job.text for job in jobs], [candidate.text for candidate in candidates])
    run.log("INFO", f"Text similarity (TF-IDF, used only to order equal scores) fitted on "
                    f"{similarity.document_count} texts, {similarity.vocabulary_size} terms.")
    rows: list[MatchRow] = []
    succeeded = failed = 0
    for index, candidate in enumerate(candidates):
        prefix = f"Candidate {str(candidate.candidate_id)[:8]}"
        try:
            scored = score_candidate(candidate, jobs, similarity.for_candidate(index), weights)
            rows.extend(scored)
            succeeded += 1
            best = max(row.score for row in scored)
            run.log("DEBUG", f"{prefix}: scored against {_plural(len(scored), 'job')} (best score {display(best):.2f}).",
                    candidate_id=str(candidate.candidate_id))
        except SoftTimeLimitExceeded:
            raise
        except Exception as exc:  # one bad candidate never stops the others (LLD §5.5)
            failed += 1
            logger.error("Match job %s: candidate %s failed: %s", run.job_id, candidate.candidate_id, safe_traceback(exc))
            run.log("ERROR", f"{prefix}: scoring failed ({type(exc).__name__}); it has no matches in this run.",
                    candidate_id=str(candidate.candidate_id))
        if run.item_done(index + 1, succeeded, failed) or run.not_running:
            break
    return rows, succeeded, failed


def run_match_job(job_id: uuid.UUID) -> str:
    """Recompute all matches. Returns the final status ("not-claimed" if the job is not queued)."""
    with session_scope() as session:
        if not progress.claim(session, job_id):
            logger.info("Match job %s is not queued (cancelled, unknown or already taken); nothing to do", job_id)
            return "not-claimed"

    run = JobRun(job_id, total=None)
    try:
        weights = Weights.from_settings(get_settings().match_weights)
        with session_scope() as session:
            jobs, candidates = load_inputs(session)
        run.total = len(candidates)
        if not candidates or not jobs:
            message = ("No candidates to match: upload resumes first." if not candidates
                       else "No jobs to match: run a crawl first.")
            run.log("ERROR", message + " The previous matches are unchanged.")
            run.finish("failed", message, progress_total=len(candidates))
            return "failed"
        no_skills = sum(1 for job in jobs if job.profile.has_no_skills)
        run.log("INFO", f"Matching started: {_plural(len(candidates), 'candidate')} × {_plural(len(jobs), 'job')} "
                        f"({len(candidates) * len(jobs)} pairs).")
        if no_skills:
            max_without_skills = display(float(weights.experience + weights.location))
            run.log("INFO", f"{no_skills} of {len(jobs)} jobs have no identified skills: they score R = 0 and N = 0, "
                            f"so at most {max_without_skills:g} points.", jobs_without_skills=no_skills)

        rows, succeeded, failed = score_all(run, jobs, candidates, weights)
        if run.not_running:
            logger.warning("Match job %s was ended elsewhere while running; its state is left unchanged", job_id)
            return "not-running"
        if run.cancel_seen:
            run.log("INFO", f"Cancelled by user after {succeeded + failed} items. The previous matches are unchanged.")
            run.finish("cancelled")
            return "cancelled"
        if succeeded == 0:
            message = f"All {_plural(failed, 'candidate')} failed."
            run.log("ERROR", message + " The previous matches are unchanged.")
            run.finish("failed", message)
            return "failed"

        run.heartbeat()  # just before the one long step that does not end an item (LLD §5.8)
        if run.not_running:
            logger.warning("Match job %s was ended elsewhere before saving; nothing was saved", job_id)
            return "not-running"
        with session_scope() as session:
            computed_at = save_matches(session, rows)
        run.log("INFO", f"Saved {_plural(len(rows), 'match', 'matches')} for {_plural(succeeded, 'candidate')}"
                        f"{f' ({failed} failed)' if failed else ''}; computed at {computed_at.isoformat()}.",
                matches=len(rows), candidates_failed=failed)
        run.finish("completed")
        return "completed"
    except SoftTimeLimitExceeded:
        run.log("ERROR", "Time limit exceeded; the match run was stopped. The previous matches are unchanged.")
        run.finish("failed", "Time limit exceeded.")
        return "failed"
    except Exception as exc:  # outside the per-candidate boundary, e.g. the database went away
        logger.error("Match job %s failed: %s", job_id, safe_traceback(exc))
        message = f"Unexpected error in the match run ({type(exc).__name__}). The previous matches are unchanged."
        try:
            run.log("ERROR", message)
            run.finish("failed", message)
        except Exception:
            logger.error("Could not record the failure of %s; the stale-job check will mark it", job_id)
        return "failed"


@celery_app.task(name="match", soft_time_limit=MATCH_SOFT_TIME_LIMIT_SECONDS, time_limit=MATCH_SOFT_TIME_LIMIT_SECONDS + 60)
def match(background_job_id: str) -> str:
    """The message carries only the job ID (ADR-004)."""
    return run_match_job(uuid.UUID(background_job_id))
