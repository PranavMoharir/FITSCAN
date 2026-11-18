"""The BFS crawl loop (LLD §5.10, ADR-008), offline with a fake site, a fake browser and an in-memory sink."""

import json

import pytest

from app.crawler.browser import RenderError
from app.crawler.frontier import Crawler, CrawlSettings, SeedRejectedError
from app.extractors.base import BaseExtractor, ExtractionResult, all_links, soup_of
from app.extractors.registry import ExtractorRegistry, get_registry
from tests.crawl_fakes import FakeRenderer, FakeSite, MemorySink, html_page, make_fetcher

BASE = "https://jobs.example.com"
ROBOTS = {BASE: "User-agent: *\nDisallow: /private/\n"}


def crawl(site, *, max_depth=3, max_pages=50, sink=None, registry=None, renderer=None, extractor=None, allowed=None):
    fetcher, _, _ = make_fetcher(site, allowed=allowed or ("jobs.example.com",))
    sink = sink or MemorySink()
    settings = CrawlSettings(f"{BASE}/", max_depth, max_pages, list(allowed or ["jobs.example.com"]), extractor)
    crawler = Crawler(settings, fetcher, registry or get_registry(), sink,
                      renderer_factory=lambda: renderer, sleep=lambda s: None)
    return crawler, crawler.run(), sink


def tree_site(**extra):
    """depth 0: /   depth 1: /a /b   depth 2: /c /d /e   depth 3: /f"""
    pages = {
        f"{BASE}/": html_page(links=["/a", "/b", "https://other.example.org/x", "/a#top", "/a?utm_source=x",
                                     "mailto:hr@example.com", "/private/admin"]),
        f"{BASE}/a": html_page(links=["/c", "/d", "/"]),
        f"{BASE}/b": html_page(links=["/e", "/a"]),
        f"{BASE}/c": html_page(links=["/f"]),
        f"{BASE}/d": html_page(),
        f"{BASE}/e": html_page(),
        f"{BASE}/f": html_page(),
    }
    pages.update(extra)
    return FakeSite(pages, robots=ROBOTS)


def test_pages_are_visited_breadth_first():
    site = tree_site()
    crawler, stats, _ = crawl(site, max_depth=3)
    order = [u.removeprefix(BASE) for u in crawler.fetch_order]
    assert order == ["/", "/a", "/b", "/private/admin", "/c", "/d", "/e", "/f"]
    assert stats.pages_skipped == 1  # /private/admin: robots.txt


def test_max_depth_is_respected():
    crawler, _, _ = crawl(tree_site(), max_depth=1)
    assert [u.removeprefix(BASE) for u in crawler.fetch_order] == ["/", "/a", "/b", "/private/admin"]


def test_max_pages_is_respected():
    crawler, stats, _ = crawl(tree_site(), max_pages=3)
    assert len(crawler.fetch_order) == 3 and stats.pages_processed == 3


def test_each_normalized_url_is_fetched_once():
    site = tree_site()
    crawl(site)
    requests = site.page_requests()
    assert len(requests) == len(set(requests))  # "/a", "/a#top" and "/a?utm_source=x" are one page


def test_only_allow_listed_domains_are_fetched():
    site = tree_site()
    crawl(site)
    assert all(u.startswith(BASE) for u in site.requests)


def test_subdomains_of_allowed_domains_are_followed():
    site = FakeSite({f"{BASE}/": html_page(links=["https://careers.jobs.example.com/open"]),
                     "https://careers.jobs.example.com/open": html_page()},
                    robots={BASE: "User-agent: *\nAllow: /\n", "https://careers.jobs.example.com": 404})
    crawler, stats, _ = crawl(site)
    assert "https://careers.jobs.example.com/open" in crawler.fetch_order and stats.pages_succeeded == 2


def test_links_to_private_addresses_are_never_requested():
    site = FakeSite({f"{BASE}/": html_page(links=["https://internal.jobs.example.com/admin"])}, robots=ROBOTS)
    _, stats, sink = crawl(site)
    assert not any("internal" in u for u in site.requests)
    assert stats.pages_skipped == 1
    assert any("private or reserved address" in m for m in sink.log.messages("INFO"))


def test_one_failing_page_does_not_stop_the_crawl():
    site = tree_site(**{f"{BASE}/a": (500, "boom"), f"{BASE}/b": html_page(links=["/e", "/missing"])})
    _, stats, sink = crawl(site)
    assert stats.pages_failed == 2  # /a (5xx after retries) and /missing (404)
    assert stats.pages_succeeded >= 2  # / and /b and /e still worked
    assert any("Failed https://jobs.example.com/a: HTTP 500" in m for m in sink.log.messages("ERROR"))
    assert sink.progress[-1][0] == stats.pages_processed  # progress reported after every page


def test_extractor_error_fails_only_that_page():
    class Fragile(BaseExtractor):
        name = "fragile"

        def parse(self, url, html):
            if url.endswith("/a"):
                raise ValueError("unexpected markup")
            return ExtractionResult(links=all_links(soup_of(html)))

    registry = ExtractorRegistry([Fragile(), get_registry().fallback])
    _, stats, sink = crawl(tree_site(), registry=registry, extractor="fragile")
    assert stats.pages_failed == 1
    assert "Could not extract from https://jobs.example.com/a: ValueError" in sink.log.messages("WARNING")
    assert stats.pages_succeeded > 1


def test_cancellation_stops_between_pages():
    crawler, stats, _ = crawl(tree_site(), sink=MemorySink(stop_after=2))
    assert stats.stopped and stats.pages_processed == 2 and len(crawler.fetch_order) == 2


def test_seed_disallowed_by_robots_txt_fails_the_whole_crawl():
    site = FakeSite({f"{BASE}/": html_page()}, robots={BASE: "User-agent: *\nDisallow: /\n"})
    with pytest.raises(SeedRejectedError, match="disallowed by robots.txt"):
        crawl(site)
    assert site.page_requests() == []


def test_seed_on_a_private_address_is_rejected():
    fetcher, _, _ = make_fetcher(FakeSite(), allowed=("internal.jobs.example.com",))
    crawler = Crawler(CrawlSettings("https://internal.jobs.example.com/", 1, 5, ["internal.jobs.example.com"]),
                      fetcher, get_registry(), MemorySink(), renderer_factory=lambda: None)
    with pytest.raises(SeedRejectedError, match="private or reserved"):
        crawler.run()


def test_redirect_to_an_already_fetched_page_is_skipped():
    site = FakeSite({f"{BASE}/": html_page(links=["/alias"]), f"{BASE}/alias": (301, "", {"location": "/"})},
                    robots=ROBOTS)
    _, stats, _ = crawl(site)
    assert stats.pages_skipped == 1 and stats.pages_succeeded == 1


def _posting(title: str | None, url: str) -> str:
    data = {"@context": "https://schema.org", "@type": "JobPosting", "url": url,
            "hiringOrganization": {"@type": "Organization", "name": "Acme"},
            "description": "<h3>Requirements</h3><ul><li>Python</li></ul>"}
    if title:
        data["title"] = title
    return f'<script type="application/ld+json">{json.dumps(data)}</script>'


def test_jobs_are_extracted_validated_and_handed_to_the_sink():
    page = html_page(body=_posting("Python Developer", f"{BASE}/jobs/1") + _posting(None, f"{BASE}/jobs/2"))
    site = FakeSite({f"{BASE}/": page}, robots=ROBOTS)
    _, stats, sink = crawl(site)
    assert (stats.jobs_extracted, stats.jobs_saved, stats.jobs_invalid) == (2, 1, 1)
    record = sink.saved[0].record
    assert (record.title, record.company, record.source, record.required_skills) == ("Python Developer", "Acme", "generic", ["Python"])
    assert any(m.startswith("Skipped an invalid job record") and "title" in m for m in sink.log.messages("WARNING"))


class NeedsJs(BaseExtractor):
    name = "needs_js"
    ready_selector = ".job"

    def needs_browser(self, url, static_html):
        return "class=\"job\"" not in static_html

    def parse(self, url, html):
        return ExtractionResult(links=all_links(soup_of(html)))


def test_browser_is_used_only_when_the_extractor_needs_it():
    site = FakeSite({f"{BASE}/": html_page(links=["/static"]), f"{BASE}/static": html_page(body='<p class="job">x</p>')},
                    robots=ROBOTS)
    renderer = FakeRenderer({f"{BASE}/": html_page(body='<p class="job">rendered</p>', links=["/static"])})
    registry = ExtractorRegistry([NeedsJs(), get_registry().fallback])
    _, stats, sink = crawl(site, registry=registry, renderer=renderer, extractor="needs_js")
    assert renderer.rendered == [(f"{BASE}/", ".job")]  # only the page whose static HTML lacked jobs
    assert renderer.closed and stats.pages_succeeded == 2


def test_a_page_that_does_not_render_is_retried_then_failed():
    site = FakeSite({f"{BASE}/": html_page()}, robots=ROBOTS)
    renderer = FakeRenderer({f"{BASE}/": [RenderError("Timeout 15000ms exceeded")]})
    registry = ExtractorRegistry([NeedsJs(), get_registry().fallback])
    _, stats, sink = crawl(site, registry=registry, renderer=renderer, extractor="needs_js")
    assert len(renderer.rendered) == 3  # 1 + max_retries (2)
    assert stats.pages_failed == 1
    assert any("did not render after 3 attempts" in m for m in sink.log.messages("ERROR"))


def test_summary_is_logged_at_the_end():
    _, stats, sink = crawl(tree_site())
    summary = sink.log.messages("INFO")[-1]
    assert summary.startswith(f"Crawl finished: {stats.pages_processed} pages processed")
    assert stats.pages_discovered == 8  # seed + a, b, private/admin, c, d, e, f
