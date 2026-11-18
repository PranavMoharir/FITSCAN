"""Offline stand-ins for the crawler's outside world: a fake website, a fake browser and a sink.

Nothing here opens a network connection: pages are served by httpx.MockTransport.
"""

from collections import defaultdict
from pathlib import Path

import httpx

from app.crawler.fetcher import Fetcher
from app.crawler.pipeline import SaveResult
from app.crawler.rate_limiter import RateLimiter

FIXTURES = Path(__file__).parent / "fixtures" / "html"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def html_page(body: str = "", links: list[str] = (), title: str = "Page") -> str:
    anchors = "".join(f'<a href="{href}">{href}</a>' for href in links)
    return f"<!doctype html><html><head><title>{title}</title></head><body>{body}{anchors}</body></html>"


class FakeSite:
    """pages maps a URL to: an HTML string (200), a (status, body[, headers]) tuple, a list of those
    (one per request, the last one repeats), or an exception to raise. Unknown URLs give 404."""

    def __init__(self, pages: dict | None = None, robots: dict | None = None, on_request=None):
        self.pages = dict(pages or {})
        self.robots = robots or {}  # origin -> robots.txt text, status int, or exception
        self.requests: list[str] = []
        self.on_request = on_request
        self._calls: dict[str, int] = defaultdict(int)

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        if self.on_request:
            self.on_request(url)
        if request.url.path == "/robots.txt":
            origin = f"{request.url.scheme}://{request.url.netloc.decode()}"
            entry = self.robots.get(origin, 404)
        else:
            entry = self.pages.get(url, (404, "<h1>Not found</h1>"))
        if isinstance(entry, list):
            index = min(self._calls[url], len(entry) - 1)
            self._calls[url] += 1
            entry = entry[index]
        if isinstance(entry, Exception) or (isinstance(entry, type) and issubclass(entry, Exception)):
            exc = entry if isinstance(entry, Exception) else entry("simulated", request=request)
            raise exc
        if isinstance(entry, int):
            return httpx.Response(entry, text="", request=request)
        if isinstance(entry, str):
            content_type = "text/plain" if request.url.path == "/robots.txt" else "text/html; charset=utf-8"
            return httpx.Response(200, text=entry, headers={"content-type": content_type}, request=request)
        status, body, *rest = entry
        headers = {"content-type": "text/html; charset=utf-8", **(rest[0] if rest else {})}
        return httpx.Response(status, text=body, headers=headers, request=request)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler), follow_redirects=False)

    def page_requests(self) -> list[str]:
        return [u for u in self.requests if not u.endswith("/robots.txt")]


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


class LogRecorder:
    def __init__(self):
        self.lines: list[tuple[str, str, dict]] = []

    def __call__(self, level: str, message: str, **context) -> None:
        self.lines.append((level, message, context))

    def messages(self, level: str | None = None) -> list[str]:
        return [m for lvl, m, _ in self.lines if level is None or lvl == level]


def make_fetcher(site: FakeSite, *, allowed=("jobs.example.com",), max_retries=2, private_allowlist=(), delay=0.0):
    clock = FakeClock()
    log = LogRecorder()
    limiter = RateLimiter(delay, clock=clock, sleep=clock.sleep)
    fetcher = Fetcher(
        site.client(), user_agent="TestBot/1.0", max_retries=max_retries, allowed_domains=list(allowed),
        private_allowlist=list(private_allowlist), rate_limiter=limiter, log=log, sleep=clock.sleep, jitter=lambda: 0.0,
    )
    return fetcher, log, clock


class MemorySink:
    """A CrawlSink that keeps everything in memory; stop_after makes page_done ask to stop."""

    def __init__(self, stop_after: int | None = None):
        self.log = LogRecorder()
        self.saved = []
        self.progress = []
        self.stop_after = stop_after

    def save(self, records):
        self.saved.extend(records)
        return SaveResult(inserted=len(records))

    def page_done(self, stats) -> bool:
        self.progress.append((stats.pages_processed, stats.pages_succeeded, stats.pages_failed))
        return self.stop_after is not None and stats.pages_processed >= self.stop_after


class FakeRenderer:
    """Returns prepared HTML for each URL (or raises), and records what was rendered."""

    def __init__(self, pages: dict[str, object]):
        self.pages = pages
        self.rendered: list[tuple[str, str | None]] = []
        self.closed = False

    def render(self, url: str, ready_selector: str | None = None) -> str:
        self.rendered.append((url, ready_selector))
        result = self.pages[url]
        if isinstance(result, list):
            result = result.pop(0) if len(result) > 1 else result[0]
        if isinstance(result, Exception):
            raise result
        return result

    def close(self) -> None:
        self.closed = True
