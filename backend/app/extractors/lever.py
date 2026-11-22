"""Lever job boards, through Lever's public Postings API (read-only, no login and no key).

Seed URL: https://api.lever.co/v0/postings/<company>?mode=json, where <company> is the name in
jobs.lever.co/<company>. One response lists every published posting, so a crawl needs one page.
api.lever.co allows crawling in its robots.txt and asks for a crawl delay of 1 second, which the
crawler honours; it checks robots.txt again on every crawl.

Fields of each posting in the response:
- `text` (the title), `hostedUrl` (the posting itself: stored as the apply URL and dedup key;
  `applyUrl` only if it is missing), `createdAt` (milliseconds since 1970);
- `categories`: `location`, `commitment` (e.g. "Full-time": the job type), `department`, `team`;
- `workplaceType`: "remote", "hybrid" or "onsite" ("remote" marks the job remote);
- `description` (HTML), `lists` (sections such as "Requirements" or "Nice to have": a heading
  and HTML list items) and `additional` (HTML): together they are the description, with the
  section headings kept, so required and nice-to-have skills can be told apart;
- `salaryRange` (optional): `min`, `max`, `currency`, `interval` ("per-year-salary", ...).
A posting does not name the company, so `company` stays unknown (the posting URL shows the
board). Anything else that is missing stays unknown too.
"""

import json
from datetime import UTC, datetime
from html import escape
from typing import Any

from app.extractors.base import BaseExtractor, ExtractionResult, RawJob

_PERIODS = ("year", "month", "week", "day", "hour")


def _text(value: Any) -> str | None:
    """A non-empty string, stripped; anything else (null, a number, a list) is unknown."""
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _created(value: Any) -> str | None:
    """`createdAt` (milliseconds since 1970, UTC) as an ISO date."""
    if not isinstance(value, int | float) or isinstance(value, bool) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _description(posting: dict) -> str | None:
    """The description, every list section under its own heading, then the closing text (HTML)."""
    parts = [posting.get("description") or ""]
    for section in posting.get("lists") or []:
        if isinstance(section, dict) and (_text(section.get("text")) or _text(section.get("content"))):
            parts.append(f"<h3>{escape(_text(section.get('text')) or '')}</h3><ul>{section.get('content') or ''}</ul>")
    parts.append(posting.get("additional") or "")
    html = "".join(part for part in parts if isinstance(part, str))
    return html.strip() or None


class LeverExtractor(BaseExtractor):
    name = "lever"
    label = "Lever job board"
    description = ("Companies that publish their openings on Lever, read through Lever's public Postings API: "
                   "one request per company.")
    domains = ("api.lever.co",)
    formats = ("json",)
    seed_template = "https://api.lever.co/v0/postings/{key}?mode=json"
    seed_key_label = "Company name on Lever"

    def parse(self, url: str, html: str) -> ExtractionResult:
        postings = json.loads(html)  # the body is JSON; a broken body fails this page only
        if not isinstance(postings, list):
            return ExtractionResult()
        return ExtractionResult(jobs=[self._job(p) for p in postings if isinstance(p, dict) and _text(p.get("text"))])

    @staticmethod
    def _job(posting: dict) -> RawJob:
        categories = posting.get("categories") if isinstance(posting.get("categories"), dict) else {}
        job = RawJob(
            title=_text(posting.get("text")),
            location=_text(categories.get("location")),
            job_type=_text(categories.get("commitment")),
            posted_date=_created(posting.get("createdAt")),
            description=_description(posting),
            apply_url=_text(posting.get("hostedUrl")) or _text(posting.get("applyUrl")),
        )
        if str(posting.get("workplaceType", "")).lower() == "remote":
            job.is_remote = True
        salary = posting.get("salaryRange")
        if isinstance(salary, dict) and (_number(salary.get("min")) is not None or _number(salary.get("max")) is not None):
            job.salary_min, job.salary_max = _number(salary.get("min")), _number(salary.get("max"))
            job.salary_currency = _text(salary.get("currency"))
            interval = str(salary.get("interval") or "").lower()
            job.salary_period = next((period for period in _PERIODS if period in interval), None)
        return job
