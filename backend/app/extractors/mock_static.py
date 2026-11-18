"""The mock site's static pages (mock-site/static/, ADR-024): plain HTML, fetched with httpx.

- Listing pages: one `li.job-card` per job, with an Apply link, plus links to the detail pages
  and to the next page.
- Detail pages: `article.job-detail` with the description, including Requirements and
  Nice-to-have sections. Both share the Apply link, so they merge into one job.
"""

from urllib.parse import urljoin, urlsplit

from app.extractors.base import BaseExtractor, ExtractionResult, RawJob, all_links, block_text, soup_of, text_of


def job_from_element(element, page_url: str) -> RawJob:
    """Fields shared by listing cards, detail pages and the rendered JavaScript cards."""
    time = element.select_one(".posted time")
    apply = element.select_one("a.apply[href]")
    return RawJob(
        title=text_of(element.select_one(".job-title")),
        company=text_of(element.select_one(".company")),
        location=text_of(element.select_one(".location")),
        job_type=text_of(element.select_one(".job-type")),
        salary_text=text_of(element.select_one(".salary")),
        posted_date=(time.get("datetime") or text_of(time)) if time else None,
        description=block_text(element.select_one(".description")),
        apply_url=urljoin(page_url, apply["href"]) if apply else None,
    )


class MockStaticExtractor(BaseExtractor):
    name = "mock_static"
    domains = ("mock-site",)

    def matches(self, url: str) -> bool:
        return super().matches(url) and urlsplit(url).path.startswith("/static/")

    def parse(self, url: str, html: str) -> ExtractionResult:
        soup = soup_of(html)
        detail = soup.select_one("article.job-detail")
        elements = [detail] if detail is not None else soup.select("li.job-card")
        return ExtractionResult(jobs=[job_from_element(el, url) for el in elements], links=all_links(soup))
