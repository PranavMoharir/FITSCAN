"""Polite HTTP fetching with httpx (LLD §5.12-5.15).

For every URL, and again for every redirect hop:
1. the host must be an allowed domain, and must not resolve to a private address (SSRF guard);
2. robots.txt must allow the URL (checked for pages, not for robots.txt itself);
3. the per-host rate limiter waits if needed;
4. the request is sent with a timeout, and retried with exponential backoff and jitter:

| Condition                  | Action                                                        |
| Timeout or connection error| Retry, up to CRAWLER_MAX_RETRIES more times                  |
| HTTP 429                   | Wait for Retry-After (capped) or back off; slow the host down |
| HTTP 5xx                   | Retry with backoff                                            |
| Other 4xx                  | No retry: the page failed                                     |
| Not HTML                   | No retry: the page is skipped                                 |
| Retries used up            | The page failed                                               |

Results are returned, never raised, so one bad page cannot stop the crawl.
"""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Literal

import httpx

from app.crawler.rate_limiter import RateLimiter
from app.crawler.robots import RobotsCache, RobotsPolicy
from app.crawler.ssrf import BlockedHostError, UnresolvableHostError, check_host
from app.crawler.urls import host_of, is_allowed_host, normalize_url

MAX_REDIRECTS = 5
MAX_PAGE_BYTES = 5 * 1024 * 1024
RETRY_AFTER_CAP_SECONDS = 60.0
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_CAP_SECONDS = 30.0
HTML_TYPES = ("text/html", "application/xhtml+xml")
REDIRECT_CODES = {301, 302, 303, 307, 308}

# log(level, message, **context): writes a background-job log line.
LogFunction = Callable[..., None]


@dataclass
class FetchResult:
    url: str
    final_url: str
    outcome: Literal["ok", "skipped", "failed"]
    status: int | None = None
    html: str | None = None
    reason: str | None = None


class PageTooLargeError(Exception):
    pass


def create_client(timeout_seconds: float) -> httpx.Client:
    """The HTTP client used by crawls. Tests replace this with a client on httpx.MockTransport."""
    return httpx.Client(timeout=timeout_seconds, follow_redirects=False)


class Fetcher:
    def __init__(
        self,
        client: httpx.Client,
        *,
        user_agent: str,
        max_retries: int,
        allowed_domains: list[str],
        private_allowlist: list[str],
        rate_limiter: RateLimiter,
        log: LogFunction,
        sleep: Callable[[float], None] | None = None,
        jitter: Callable[[], float] | None = None,
    ):
        self.client = client
        self.user_agent = user_agent
        self.attempts = max_retries + 1
        self.allowed_domains = allowed_domains
        self.private_allowlist = private_allowlist
        self.rate_limiter = rate_limiter
        self.log = log
        self._sleep = sleep or time.sleep
        self._jitter = jitter or random.random
        self.robots = RobotsCache(self._fetch_robots, user_agent, on_new_host=self._robots_loaded)

    # --- public -------------------------------------------------------------------------------

    def fetch_page(self, url: str) -> FetchResult:
        return self._get(url, check_robots=True, html_only=True)

    def check_url(self, url: str) -> str | None:
        """Why the URL may not be contacted (allow-list or SSRF), or None if it may."""
        host = host_of(url)
        if not is_allowed_host(host, self.allowed_domains):
            return "outside the allowed domains"
        try:
            check_host(host, self.private_allowlist)
        except (BlockedHostError, UnresolvableHostError) as exc:
            return str(exc)
        return None

    # --- robots.txt ------------------------------------------------------------------------

    def _fetch_robots(self, robots_url: str) -> tuple[int, str]:
        result = self._get(robots_url, check_robots=False, html_only=False)
        if result.status is None:
            raise ConnectionError(result.reason or "robots.txt could not be fetched")
        return result.status, result.html or ""

    def _robots_loaded(self, robots_url: str, policy: RobotsPolicy) -> None:
        host = host_of(robots_url)
        if policy.reason:
            self.log("WARNING", f"All of {host} is treated as disallowed: {policy.reason}", host=host)
            return
        delay = policy.crawl_delay(self.user_agent)
        self.rate_limiter.use_crawl_delay(host, delay)
        self.log("INFO", f"Loaded robots.txt for {host}", host=host, crawl_delay=delay)

    # --- requests ------------------------------------------------------------------------------

    def _get(self, url: str, *, check_robots: bool, html_only: bool) -> FetchResult:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            refusal = self.check_url(current)
            if refusal:
                outcome = "failed" if refusal.startswith("could not resolve") else "skipped"
                return FetchResult(url, current, outcome, reason=refusal)
            if check_robots and not self.robots.allowed(current):
                return FetchResult(url, current, "skipped", reason="disallowed by robots.txt")

            response = self._request(current)
            if isinstance(response, str):
                return FetchResult(url, current, "failed", reason=response)
            status, headers, body = response

            if status in REDIRECT_CODES:
                target = normalize_url(headers.get("location", ""), base=current)
                if target is None:
                    return FetchResult(url, current, "failed", status, reason="redirect to an invalid URL")
                self.log("DEBUG", f"Redirected {current} -> {target} ({status})")
                current = target
                continue
            if 200 <= status < 300:
                content_type = headers.get("content-type", "").split(";")[0].strip().lower()
                if html_only and content_type not in HTML_TYPES:
                    return FetchResult(url, current, "skipped", status, reason=f"not HTML ({content_type or 'unknown type'})")
                return FetchResult(url, current, "ok", status, html=body)
            return FetchResult(url, current, "failed", status, html=body, reason=f"HTTP {status}")
        return FetchResult(url, current, "failed", reason=f"more than {MAX_REDIRECTS} redirects")

    def _request(self, url: str) -> tuple[int, httpx.Headers, str] | str:
        """Send GET with retries. Returns (status, headers, body), or a failure reason."""
        host = host_of(url)
        for attempt in range(1, self.attempts + 1):
            self.rate_limiter.wait(host)
            try:
                status, headers, body = self._send(url)
            except httpx.TimeoutException:
                problem = "Timeout"
            except httpx.TransportError:
                problem = "Connection error"
            except PageTooLargeError:
                return f"page larger than {MAX_PAGE_BYTES // (1024 * 1024)} MB"
            else:
                if status == 429:
                    wait = self._retry_after(headers)
                    wait = self._backoff(attempt) if wait is None else wait
                    self.rate_limiter.slow_down(host)
                    if attempt < self.attempts:
                        self.log("WARNING", f"Rate limited (429) on {url}, waiting {wait:.1f} s "
                                            f"(attempt {attempt}/{self.attempts})", attempt=attempt)
                        self._sleep(wait)
                        continue
                    return f"HTTP 429 after {self.attempts} attempts"
                if 500 <= status < 600:
                    if attempt < self.attempts:
                        wait = self._backoff(attempt)
                        self.log("WARNING", f"HTTP {status} on attempt {attempt}/{self.attempts} for {url}, "
                                            f"retrying in {wait:.1f} s", attempt=attempt, status=status)
                        self._sleep(wait)
                        continue
                    return f"HTTP {status} after {self.attempts} attempts"
                return status, headers, body

            if attempt < self.attempts:
                wait = self._backoff(attempt)
                self.log("WARNING", f"{problem} on attempt {attempt}/{self.attempts} for {url}, "
                                    f"retrying in {wait:.1f} s", attempt=attempt)
                self._sleep(wait)
                continue
            return f"{problem.lower()} after {self.attempts} attempts"
        raise AssertionError("unreachable")

    def _send(self, url: str) -> tuple[int, httpx.Headers, str]:
        headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"}
        with self.client.stream("GET", url, headers=headers) as response:
            declared = response.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > MAX_PAGE_BYTES:
                raise PageTooLargeError
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_PAGE_BYTES:
                    raise PageTooLargeError
                chunks.append(chunk)
            body = b"".join(chunks).decode(response.charset_encoding or "utf-8", errors="replace")
            return response.status_code, response.headers, body

    def _backoff(self, attempt: int) -> float:
        """About 1 s, 2 s, 4 s ... plus up to 25 % random jitter, so retries do not happen in lock-step."""
        delay = min(BACKOFF_BASE_SECONDS * 2 ** (attempt - 1), BACKOFF_CAP_SECONDS)
        return delay * (1 + 0.25 * self._jitter())

    @staticmethod
    def _retry_after(headers: httpx.Headers) -> float | None:
        value = headers.get("retry-after")
        if not value:
            return None
        value = value.strip()
        if value.isdigit():
            seconds = float(value)
        else:
            try:
                seconds = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
            except (TypeError, ValueError):
                return None
        return max(0.0, min(seconds, RETRY_AFTER_CAP_SECONDS))
