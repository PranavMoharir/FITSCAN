"""Fake Python Jobs (https://realpython.github.io/fake-jobs/), the static job board the brief suggests.

- Listing page: one card per job (title, company, location, date) with an "Apply" link to the
  job's detail page. Those links are the only ones followed.
- Detail page: the same fields plus the description. The page itself is the apply URL, so the
  listing card and the detail page share a dedup_key and merge into one job.
"""

from urllib.parse import urljoin

from app.extractors.base import BaseExtractor, ExtractionResult, RawJob, block_text, soup_of, text_of


def _without_label(text: str | None, label: str) -> str | None:
    if text and text.lower().startswith(label.lower()):
        text = text[len(label):].strip()
    return text or None


class FakePythonJobsExtractor(BaseExtractor):
    name = "fake_python_jobs"
    domains = ("realpython.github.io",)

    def matches(self, url: str) -> bool:
        return super().matches(url) and "/fake-jobs" in url

    def parse(self, url: str, html: str) -> ExtractionResult:
        soup = soup_of(html)
        box = soup.select_one("div.box")
        if box is not None and box.select_one("h1.title"):
            return self._detail(url, box)

        jobs, links = [], []
        for card in soup.select("div.card-content"):
            apply_link = next((a["href"] for a in card.select("a[href]") if text_of(a) == "Apply"), None)
            time = card.select_one("time")
            jobs.append(RawJob(
                title=text_of(card.select_one("h2.title")),
                company=text_of(card.select_one("h3.company")),
                location=text_of(card.select_one("p.location")),
                posted_date=(time.get("datetime") or text_of(time)) if time else None,
                apply_url=urljoin(url, apply_link) if apply_link else None,
            ))
            if apply_link:
                links.append(apply_link)
        return ExtractionResult(jobs=jobs, links=links)

    def _detail(self, url: str, box) -> ExtractionResult:
        content = box.select_one("div.content")
        paragraphs = [p for p in content.find_all("p", recursive=False) if not p.get("id")] if content else []
        job = RawJob(
            title=text_of(box.select_one("h1.title")),
            company=text_of(box.select_one("h2.company")),
            location=_without_label(text_of(box.select_one("#location")), "Location:"),
            posted_date=_without_label(text_of(box.select_one("#date")), "Posted:"),
            description="\n".join(filter(None, (block_text(p) for p in paragraphs))) or None,
            apply_url=url,
        )
        return ExtractionResult(jobs=[job], links=[])
