"""Per-host minimum interval between requests, for one crawl (LLD §5.14, ADR-010).

- The interval starts at CRAWLER_DEFAULT_DELAY_SECONDS.
- A robots.txt Crawl-delay that is longer replaces it for that host.
- An HTTP 429 doubles the interval for the rest of the crawl (up to MAX_DELAY_SECONDS).
The clock and the sleep function can be replaced, so tests run instantly.
"""

import time
from collections.abc import Callable

MAX_DELAY_SECONDS = 60.0


class RateLimiter:
    def __init__(
        self,
        default_delay: float,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ):
        self.default_delay = default_delay
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._delays: dict[str, float] = {}
        self._last_request: dict[str, float] = {}

    def delay_for(self, host: str) -> float:
        return self._delays.get(host, self.default_delay)

    def use_crawl_delay(self, host: str, seconds: float | None) -> None:
        if seconds is not None and seconds > self.delay_for(host):
            self._delays[host] = min(seconds, MAX_DELAY_SECONDS)

    def slow_down(self, host: str) -> float:
        """After a 429: double this host's interval. Returns the new interval."""
        self._delays[host] = min(max(self.delay_for(host), 0.5) * 2, MAX_DELAY_SECONDS)
        return self._delays[host]

    def wait(self, host: str) -> float:
        """Sleep until this host may be contacted again, then record the request. Returns seconds slept."""
        waited = 0.0
        last = self._last_request.get(host)
        if last is not None:
            remaining = self.delay_for(host) - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
                waited = remaining
        self._last_request[host] = self._clock()
        return waited
