"""The mock site's JavaScript page (mock-site/dynamic/, ADR-024).

The server sends an empty `#jobs` container; a script fills it after the page loads. So the
static HTML has no jobs, `needs_browser` says so, and the crawler renders the page with
Playwright before calling `parse` again on the rendered HTML (LLD §5.16 "static first").
"""

from urllib.parse import urlsplit

from app.extractors.base import BaseExtractor, ExtractionResult, all_links, soup_of
from app.extractors.mock_static import job_from_element


class MockDynamicExtractor(BaseExtractor):
    name = "mock_dynamic"
    label = "Demo: FITSCAN mock site (JavaScript page)"
    description = "Invented jobs that the mock site adds with JavaScript (rendered in a headless browser). Never real openings."
    demo = True
    domains = ("mock-site",)
    example_seed = "http://mock-site:8080/dynamic/index.html"
    ready_selector = "#jobs .job-card"  # the browser waits until the script has added the jobs

    def matches(self, url: str) -> bool:
        return super().matches(url) and urlsplit(url).path.startswith("/dynamic/")

    def needs_browser(self, url: str, static_html: str) -> bool:
        container = soup_of(static_html).select_one("#jobs")
        return container is not None and container.select_one(".job-card") is None

    def parse(self, url: str, html: str) -> ExtractionResult:
        soup = soup_of(html)
        cards = soup.select("#jobs .job-card")
        return ExtractionResult(jobs=[job_from_element(card, url) for card in cards], links=all_links(soup))
