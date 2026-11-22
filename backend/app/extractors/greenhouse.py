"""Greenhouse job boards, through Greenhouse's public Job Board API (read-only, no login and no key).

Seed URL: https://boards-api.greenhouse.io/v1/boards/<board token>/jobs?content=true, where the
board token is the name in boards.greenhouse.io/<token> or job-boards.greenhouse.io/<token>. One
response lists every open job of the board with its description, so a crawl needs one page.
boards-api.greenhouse.io allows crawling in its robots.txt (only /embed/ is disallowed), and the
crawler checks that again on every crawl.

Fields of each job in the response ("List jobs" with content=true):
- `title`, `company_name`, `location.name`;
- `absolute_url`: the posting itself (stored as the apply URL; it is also the dedup key);
- `first_published` (else `updated_at`): an ISO date and time;
- `content`: the description as HTML whose tags are entity-escaped (`&lt;p&gt;`);
- `metadata`: the board's custom fields, or null; an "Employment Type" field gives the job type.
The API has no salary or experience fields. The pipeline still reads a minimum experience from
the description ("3+ years of experience"); anything else that is missing stays unknown.
"""

import json
from typing import Any

from app.extractors.base import BaseExtractor, ExtractionResult, RawJob

_JOB_TYPE_FIELDS = ("employment type", "job type", "employment", "commitment")


def _metadata_value(metadata: Any, names: tuple[str, ...]) -> str | None:
    """The value of the first custom field whose name is one of `names`, e.g. "Full-time"."""
    if not isinstance(metadata, list):
        return None
    for item in metadata:
        if isinstance(item, dict) and str(item.get("name", "")).strip().lower() in names:
            value = item.get("value")
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value if v)
            text = str(value).strip() if value else ""
            return text or None
    return None


def _text(value: Any) -> str | None:
    """A non-empty string, stripped; anything else (null, a number, a list) is unknown."""
    if not isinstance(value, str):
        return None
    return value.strip() or None


class GreenhouseExtractor(BaseExtractor):
    name = "greenhouse"
    label = "Greenhouse job board"
    description = ("Companies that publish their openings on Greenhouse, read through Greenhouse's public "
                   "Job Board API: one request per board.")
    domains = ("boards-api.greenhouse.io",)
    formats = ("json",)
    seed_template = "https://boards-api.greenhouse.io/v1/boards/{key}/jobs?content=true"
    seed_key_label = "Board token"

    def parse(self, url: str, html: str) -> ExtractionResult:
        data = json.loads(html)  # the body is JSON; a broken body fails this page only
        postings = data.get("jobs") if isinstance(data, dict) else None
        if not isinstance(postings, list):
            return ExtractionResult()
        return ExtractionResult(jobs=[self._job(p) for p in postings if isinstance(p, dict) and _text(p.get("title"))])

    @staticmethod
    def _job(posting: dict) -> RawJob:
        location = posting.get("location")
        return RawJob(
            title=_text(posting.get("title")),
            company=_text(posting.get("company_name")),
            location=_text(location.get("name")) if isinstance(location, dict) else None,
            job_type=_metadata_value(posting.get("metadata"), _JOB_TYPE_FIELDS),
            posted_date=_text(posting.get("first_published")) or _text(posting.get("updated_at")),
            description=_text(posting.get("content")),
            apply_url=_text(posting.get("absolute_url")),
        )
