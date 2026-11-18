"""Fetching rules: retries, 429/5xx/4xx, redirects, robots.txt and rate limiting (LLD §5.12-5.15).

Every test uses httpx.MockTransport and a fake clock, so nothing touches the network or sleeps.
"""

import httpx

from app.crawler.fetcher import MAX_PAGE_BYTES
from app.crawler.rate_limiter import RateLimiter
from tests.crawl_fakes import FakeClock, FakeSite, make_fetcher

BASE = "https://jobs.example.com"
ROBOTS_OK = {BASE: "User-agent: *\nDisallow: /private/\n"}


def test_success_returns_html():
    site = FakeSite({f"{BASE}/": "<h1>Jobs</h1>"}, robots=ROBOTS_OK)
    fetcher, _, clock = make_fetcher(site)
    result = fetcher.fetch_page(f"{BASE}/")
    assert (result.outcome, result.status, result.html) == ("ok", 200, "<h1>Jobs</h1>")
    assert clock.sleeps == []


def test_timeouts_are_retried_with_exponential_backoff():
    site = FakeSite({f"{BASE}/": [httpx.ReadTimeout, httpx.ConnectTimeout, "<p>finally</p>"]}, robots=ROBOTS_OK)
    fetcher, log, clock = make_fetcher(site, max_retries=2)
    result = fetcher.fetch_page(f"{BASE}/")
    assert result.outcome == "ok"
    assert site.page_requests().count(f"{BASE}/") == 3
    assert clock.sleeps == [1.0, 2.0]  # 1 s, then 2 s (jitter is 0 in tests)
    assert log.messages("WARNING")[0].startswith("Timeout on attempt 1/3")


def test_retries_used_up_marks_the_page_failed():
    site = FakeSite({f"{BASE}/": httpx.ConnectError}, robots=ROBOTS_OK)
    fetcher, _, clock = make_fetcher(site, max_retries=2)
    result = fetcher.fetch_page(f"{BASE}/")
    assert (result.outcome, result.reason) == ("failed", "connection error after 3 attempts")
    assert clock.sleeps == [1.0, 2.0]


def test_429_waits_for_retry_after_and_slows_the_host_down():
    site = FakeSite({f"{BASE}/": [(429, "slow down", {"retry-after": "7"}), "<p>ok</p>"]}, robots=ROBOTS_OK)
    fetcher, log, clock = make_fetcher(site, delay=1.0)
    result = fetcher.fetch_page(f"{BASE}/")
    assert result.outcome == "ok"
    assert 7.0 in clock.sleeps
    assert fetcher.rate_limiter.delay_for("jobs.example.com") == 2.0  # doubled for the rest of the crawl
    assert any("Rate limited (429)" in m for m in log.messages("WARNING"))


def test_429_retry_after_is_capped_and_http_dates_are_understood():
    site = FakeSite({f"{BASE}/": [(429, "", {"retry-after": "3600"}), (429, "", {"retry-after": "Wed, 21 Oct 2015 07:28:00 GMT"}),
                                  "<p>ok</p>"]}, robots=ROBOTS_OK)
    fetcher, _, clock = make_fetcher(site)
    assert fetcher.fetch_page(f"{BASE}/").outcome == "ok"
    assert clock.sleeps[:2] == [60.0, 0.0]  # capped at 60 s; a date in the past means "now"


def test_5xx_is_retried_then_succeeds():
    site = FakeSite({f"{BASE}/": [(503, "busy"), (502, "bad gateway"), "<p>ok</p>"]}, robots=ROBOTS_OK)
    fetcher, log, clock = make_fetcher(site, max_retries=2)
    assert fetcher.fetch_page(f"{BASE}/").outcome == "ok"
    assert clock.sleeps == [1.0, 2.0]
    assert "HTTP 503 on attempt 1/3" in log.messages("WARNING")[0]


def test_5xx_after_every_retry_fails_the_page():
    site = FakeSite({f"{BASE}/": (500, "error")}, robots=ROBOTS_OK)
    fetcher, _, _ = make_fetcher(site, max_retries=1)
    result = fetcher.fetch_page(f"{BASE}/")
    assert (result.outcome, result.reason) == ("failed", "HTTP 500 after 2 attempts")


def test_permanent_4xx_is_not_retried():
    site = FakeSite({f"{BASE}/gone": (404, "nope"), f"{BASE}/secret": (403, "no")}, robots=ROBOTS_OK)
    fetcher, _, clock = make_fetcher(site, max_retries=3)
    for path, status in (("/gone", 404), ("/secret", 403)):
        result = fetcher.fetch_page(f"{BASE}{path}")
        assert (result.outcome, result.status, result.reason) == ("failed", status, f"HTTP {status}")
        assert site.page_requests().count(f"{BASE}{path}") == 1
    assert clock.sleeps == []


def test_non_html_content_is_skipped():
    site = FakeSite({f"{BASE}/file.pdf": (200, "%PDF-1.7", {"content-type": "application/pdf"})}, robots=ROBOTS_OK)
    fetcher, _, _ = make_fetcher(site)
    result = fetcher.fetch_page(f"{BASE}/file.pdf")
    assert (result.outcome, result.reason) == ("skipped", "not HTML (application/pdf)")


def test_oversized_page_fails():
    site = FakeSite({f"{BASE}/big": (200, "x", {"content-length": str(MAX_PAGE_BYTES + 1)})}, robots=ROBOTS_OK)
    fetcher, _, _ = make_fetcher(site)
    assert fetcher.fetch_page(f"{BASE}/big").outcome == "failed"


def test_redirects_are_followed_and_every_hop_is_checked():
    site = FakeSite({
        f"{BASE}/old": (301, "", {"location": "/new"}),
        f"{BASE}/new": "<p>new home</p>",
        f"{BASE}/out": (302, "", {"location": "https://other.example.org/x"}),
        f"{BASE}/inside": (302, "", {"location": "https://internal.jobs.example.com/admin"}),
        f"{BASE}/hidden": (302, "", {"location": "/private/page"}),
        f"{BASE}/loop": (302, "", {"location": "/loop"}),
    }, robots=ROBOTS_OK)
    fetcher, _, _ = make_fetcher(site)

    moved = fetcher.fetch_page(f"{BASE}/old")
    assert (moved.outcome, moved.final_url, moved.html) == ("ok", f"{BASE}/new", "<p>new home</p>")
    assert fetcher.fetch_page(f"{BASE}/out").reason == "outside the allowed domains"
    assert "private or reserved address" in fetcher.fetch_page(f"{BASE}/inside").reason  # SSRF on a redirect hop
    assert fetcher.fetch_page(f"{BASE}/hidden").reason == "disallowed by robots.txt"     # robots on a redirect hop
    assert fetcher.fetch_page(f"{BASE}/loop").reason == "more than 5 redirects"
    assert "https://other.example.org/x" not in site.requests
    assert not any("internal.jobs.example.com" in u for u in site.requests)


def test_private_and_external_hosts_are_never_requested():
    site = FakeSite({}, robots=ROBOTS_OK)
    fetcher, _, _ = make_fetcher(site, allowed=("jobs.example.com", "internal.jobs.example.com"))
    assert fetcher.fetch_page("https://internal.jobs.example.com/").outcome == "skipped"
    assert fetcher.fetch_page("https://elsewhere.example.net/").reason == "outside the allowed domains"
    assert site.requests == []


def test_robots_disallowed_page_is_skipped_without_a_request():
    site = FakeSite({f"{BASE}/private/x": "<p>secret</p>"}, robots=ROBOTS_OK)
    fetcher, _, _ = make_fetcher(site)
    assert fetcher.fetch_page(f"{BASE}/private/x").reason == "disallowed by robots.txt"
    assert site.page_requests() == []


def test_robots_txt_is_fetched_once_per_host():
    site = FakeSite({f"{BASE}/a": "a", f"{BASE}/b": "b"}, robots=ROBOTS_OK)
    fetcher, _, _ = make_fetcher(site)
    fetcher.fetch_page(f"{BASE}/a")
    fetcher.fetch_page(f"{BASE}/b")
    assert site.requests.count(f"{BASE}/robots.txt") == 1


def test_missing_robots_txt_allows_everything():
    site = FakeSite({f"{BASE}/private/x": "<p>ok</p>"}, robots={BASE: 404})
    fetcher, _, _ = make_fetcher(site)
    assert fetcher.fetch_page(f"{BASE}/private/x").outcome == "ok"


def test_robots_txt_5xx_or_unreachable_disallows_the_whole_host():
    for robots in (500, httpx.ConnectError):
        site = FakeSite({f"{BASE}/": "<p>home</p>"}, robots={BASE: robots})
        fetcher, log, _ = make_fetcher(site, max_retries=0)
        result = fetcher.fetch_page(f"{BASE}/")
        assert (result.outcome, result.reason) == ("skipped", "disallowed by robots.txt")
        assert any("treated as disallowed" in m for m in log.messages("WARNING"))
        assert site.page_requests() == []


def test_crawl_delay_from_robots_txt_raises_the_interval():
    site = FakeSite({f"{BASE}/a": "a", f"{BASE}/b": "b"}, robots={BASE: "User-agent: *\nCrawl-delay: 5\n"})
    fetcher, _, clock = make_fetcher(site, delay=1.0)
    fetcher.fetch_page(f"{BASE}/a")
    fetcher.fetch_page(f"{BASE}/b")
    assert fetcher.rate_limiter.delay_for("jobs.example.com") == 5.0
    assert 5.0 in clock.sleeps


# --- Rate limiter ------------------------------------------------------------------------------


def test_rate_limiter_keeps_a_minimum_interval_per_host():
    clock = FakeClock()
    limiter = RateLimiter(2.0, clock=clock, sleep=clock.sleep)
    assert limiter.wait("a.example.com") == 0  # first request: no wait
    assert limiter.wait("a.example.com") == 2.0
    assert limiter.wait("b.example.com") == 0  # other hosts are independent
    clock.now += 5
    assert limiter.wait("a.example.com") == 0  # enough time has passed
    assert clock.sleeps == [2.0]


def test_rate_limiter_crawl_delay_and_slow_down():
    limiter = RateLimiter(1.0, clock=FakeClock(), sleep=lambda s: None)
    limiter.use_crawl_delay("a.example.com", 0.5)  # shorter than the default: ignored
    assert limiter.delay_for("a.example.com") == 1.0
    limiter.use_crawl_delay("a.example.com", 3)
    assert limiter.delay_for("a.example.com") == 3.0
    assert limiter.slow_down("a.example.com") == 6.0
    for _ in range(10):
        limiter.slow_down("a.example.com")
    assert limiter.delay_for("a.example.com") == 60.0  # capped
