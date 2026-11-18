"""The breadth-first crawl loop and the per-page pipeline (LLD §5.10, ADR-008).

    frontier = queue[(normalize(seed), 0)]      # FIFO queue of (url, depth)
    visited  = {normalize(seed)}                # URLs already queued or fetched
    while frontier and pages_processed < max_pages and not cancelled:
        url, depth = frontier.popleft()
        fetch -> extract (browser only if needed) -> normalize, skills, validate -> save
        if depth < max_depth: queue new allowed links at depth + 1

Every URL taken from the queue counts as processed, whether it succeeded, failed or was
skipped. Each page is handled inside its own error boundary, so one bad page never stops the
crawl. The crawler does not touch the database itself: it reports through a `CrawlSink`
(the Celery task's implementation writes progress, logs and jobs to PostgreSQL).
"""

import time
from collections import Counter, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from pydantic import ValidationError

from app.crawler.browser import RenderError
from app.crawler.fetcher import Fetcher
from app.crawler.pipeline import BuiltRecord, SaveResult, build_record
from app.crawler.urls import host_of, is_allowed_host, normalize_url
from app.extractors.base import BaseExtractor
from app.extractors.registry import ExtractorRegistry


@dataclass
class CrawlSettings:
    seed_url: str
    max_depth: int
    max_pages: int
    allowed_domains: list[str]
    extractor: str | None = None   # force this extractor for every page


@dataclass
class CrawlStats:
    pages_processed: int = 0   # URLs taken from the queue (the job's progress)
    pages_succeeded: int = 0
    pages_failed: int = 0
    pages_skipped: int = 0     # robots.txt, non-HTML, blocked host, duplicate after redirect
    pages_discovered: int = 0  # URLs queued so far, the seed included
    jobs_extracted: int = 0
    jobs_saved: int = 0
    jobs_invalid: int = 0
    stopped: bool = False      # the sink asked the crawl to stop (cancelled, or job no longer running)
    current_url: str | None = None
    unmatched_terms: Counter = field(default_factory=Counter)


class CrawlSink(Protocol):
    def log(self, level: str, message: str, **context) -> None: ...
    def save(self, records: list[BuiltRecord]) -> SaveResult: ...
    def page_done(self, stats: CrawlStats) -> bool: ...  # True means: stop the crawl


class Renderer(Protocol):
    def render(self, url: str, ready_selector: str | None = None) -> str: ...
    def close(self) -> None: ...


class SeedRejectedError(Exception):
    """The seed URL cannot be crawled at all, so the whole job fails."""


class RenderFailedError(Exception):
    pass


def _short_errors(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'record'}: {e['msg']}" for e in exc.errors()[:3])


class Crawler:
    def __init__(
        self,
        settings: CrawlSettings,
        fetcher: Fetcher,
        registry: ExtractorRegistry,
        sink: CrawlSink,
        renderer_factory: Callable[[], Renderer],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] | None = None,
    ):
        self.settings = settings
        self.fetcher = fetcher
        self.registry = registry
        self.sink = sink
        self._renderer_factory = renderer_factory
        self._renderer: Renderer | None = None
        self._clock = clock
        self._sleep = sleep or time.sleep
        self.stats = CrawlStats()
        self.fetch_order: list[str] = []  # URLs in the order they were taken from the queue

    def run(self) -> CrawlStats:
        seed = normalize_url(self.settings.seed_url)
        if seed is None:
            raise SeedRejectedError(f"Seed URL {self.settings.seed_url} is not a valid http(s) URL.")
        refusal = self.fetcher.check_url(seed)
        if refusal:
            raise SeedRejectedError(f"Seed URL {seed} cannot be crawled: {refusal}.")
        if not self.fetcher.robots.allowed(seed):
            raise SeedRejectedError(f"Seed URL {seed} is disallowed by robots.txt.")

        frontier: deque[tuple[str, int]] = deque([(seed, 0)])
        self._visited = {seed}
        self.stats.pages_discovered = 1
        try:
            while frontier and self.stats.pages_processed < self.settings.max_pages:
                url, depth = frontier.popleft()
                self.fetch_order.append(url)
                self.stats.pages_processed += 1
                self.stats.current_url = url
                self._process_page(url, depth, frontier)
                if self.sink.page_done(self.stats):
                    self.stats.stopped = True
                    break
        finally:
            if self._renderer is not None:
                self._renderer.close()
        self._log_summary()
        return self.stats

    # --- one page ----------------------------------------------------------------------------

    def _process_page(self, url: str, depth: int, frontier: deque) -> None:
        stats, log = self.stats, self.sink.log
        result = self.fetcher.fetch_page(url)
        if result.outcome == "skipped":
            stats.pages_skipped += 1
            log("INFO", f"Skipped {url}: {result.reason}", url=url, depth=depth)
            return
        if result.outcome == "failed":
            stats.pages_failed += 1
            log("ERROR", f"Failed {url}: {result.reason}", url=url, depth=depth, status=result.status)
            return

        final_url = result.final_url
        if final_url != url and final_url in self._visited:
            stats.pages_skipped += 1
            log("INFO", f"Skipped {url}: redirects to {final_url}, which is already queued or fetched", url=url)
            return
        self._visited.add(final_url)

        extractor = self.registry.select(final_url, self.settings.extractor)
        rendered = False
        try:
            html = result.html or ""
            if extractor.render_mode == "browser" or extractor.needs_browser(final_url, html):
                html = self._render(final_url, extractor)
                rendered = True
            extraction = extractor.parse(final_url, html)
        except RenderFailedError as exc:
            stats.pages_failed += 1
            log("ERROR", f"Failed {final_url}: {exc}", url=final_url, depth=depth)
            return
        except Exception as exc:  # a broken page or extractor affects only this page
            stats.pages_failed += 1
            log("WARNING", f"Could not extract from {final_url}: {type(exc).__name__}", url=final_url, depth=depth)
            return

        records = self._build_records(extraction.jobs, final_url, extractor)
        saved = self.sink.save(records) if records else SaveResult()  # database errors end the job
        stats.jobs_extracted += len(extraction.jobs)
        stats.jobs_saved += saved.saved
        stats.pages_succeeded += 1

        new_links = ignored = 0
        if depth < self.settings.max_depth:
            for link in extraction.links:
                target = normalize_url(link, base=final_url)
                if target is None or target in self._visited:
                    continue
                if not is_allowed_host(host_of(target), self.settings.allowed_domains):
                    ignored += 1
                    continue
                self._visited.add(target)
                frontier.append((target, depth + 1))
                new_links += 1
        stats.pages_discovered = len(self._visited)
        if ignored:
            log("DEBUG", f"Ignored {ignored} links outside the allowed domains on {final_url}", url=final_url)
        log(
            "INFO",
            f"Fetched {final_url} ({result.status}): {len(extraction.jobs)} jobs extracted, "
            f"{saved.saved} saved ({saved.inserted} new, {saved.updated} updated), {new_links} new links",
            url=final_url, depth=depth, status=result.status, rendered=rendered, extractor=extractor.name,
            jobs_extracted=len(extraction.jobs), jobs_saved=saved.saved, new_links=new_links,
        )

    def _build_records(self, raw_jobs, page_url: str, extractor: BaseExtractor) -> list[BuiltRecord]:
        records = []
        fetched_at = self._clock()
        for raw in raw_jobs:
            try:
                built = build_record(raw, page_url=page_url, source=extractor.name, fetched_at=fetched_at)
            except ValidationError as exc:
                self.stats.jobs_invalid += 1
                self.sink.log("WARNING", f"Skipped an invalid job record from {page_url}: {_short_errors(exc)}", url=page_url)
                continue
            for warning in built.warnings:
                self.sink.log("WARNING", f"{built.record.title}: {warning} on {page_url}", url=page_url)
            self.stats.unmatched_terms.update(built.unmatched_terms)
            records.append(built)
        return records

    def _render(self, url: str, extractor: BaseExtractor) -> str:
        """Render with a headless browser; retried like a network failure (LLD §9.4)."""
        if self._renderer is None:
            self._renderer = self._renderer_factory()
        self.sink.log("INFO", f"Rendering {url} in a headless browser (the page needs JavaScript)", url=url)
        attempts = self.fetcher.attempts
        for attempt in range(1, attempts + 1):
            self.fetcher.rate_limiter.wait(host_of(url))
            try:
                return self._renderer.render(url, extractor.ready_selector)
            except RenderError as exc:
                if attempt == attempts:
                    raise RenderFailedError(f"the page did not render after {attempts} attempts ({exc})") from exc
                wait = self.fetcher._backoff(attempt)
                self.sink.log("WARNING", f"Rendering failed on attempt {attempt}/{attempts} for {url}, "
                                         f"retrying in {wait:.1f} s", url=url, attempt=attempt)
                self._sleep(wait)
        raise AssertionError("unreachable")

    def _log_summary(self) -> None:
        s = self.stats
        self.sink.log(
            "INFO",
            f"Crawl finished: {s.pages_processed} pages processed ({s.pages_succeeded} succeeded, "
            f"{s.pages_failed} failed, {s.pages_skipped} skipped), {s.pages_discovered} discovered, "
            f"{s.jobs_extracted} jobs extracted, {s.jobs_saved} saved, {s.jobs_invalid} invalid",
            pages_processed=s.pages_processed, pages_succeeded=s.pages_succeeded, pages_failed=s.pages_failed,
            pages_skipped=s.pages_skipped, pages_discovered=s.pages_discovered, jobs_extracted=s.jobs_extracted,
            jobs_saved=s.jobs_saved, jobs_invalid=s.jobs_invalid,
        )
        if s.unmatched_terms:
            top = ", ".join(f"{term} ({count})" for term, count in s.unmatched_terms.most_common(10))
            self.sink.log("INFO", f"Skill-like terms not in the taxonomy: {top}")
