"""Generic fallback: schema.org `JobPosting` JSON-LD, which many job sites embed (LLD §5.16).

Pages without JobPosting data give no jobs; their links are still returned, so the crawl goes on.
"""

import json
from typing import Any

from app.extractors.base import BaseExtractor, ExtractionResult, RawJob, all_links, soup_of


def _items(data: Any):
    """Every JSON object in the document, including those inside lists and "@graph"."""
    if isinstance(data, list):
        for item in data:
            yield from _items(item)
    elif isinstance(data, dict):
        yield data
        for key in ("@graph", "itemListElement"):
            if key in data:
                yield from _items(data[key])


def _is_job_posting(item: dict) -> bool:
    kind = item.get("@type")
    return kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind)


def _name(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("name")
    return str(value).strip() if value else None


def _location(posting: dict) -> str | None:
    locations = posting.get("jobLocation")
    if isinstance(locations, list):
        locations = locations[0] if locations else None
    address = locations.get("address") if isinstance(locations, dict) else None
    if isinstance(address, str):
        return address
    if isinstance(address, dict):
        parts = [address.get("addressLocality"), address.get("addressRegion"), _name(address.get("addressCountry"))]
        return ", ".join(str(p) for p in parts if p) or None
    return None


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_raw_job(posting: dict, page_url: str) -> RawJob:
    job = RawJob(
        title=_name(posting.get("title")),
        company=_name(posting.get("hiringOrganization")),
        location=_location(posting),
        posted_date=posting.get("datePosted"),
        description=posting.get("description"),
        apply_url=posting.get("url") or page_url,
    )
    employment = posting.get("employmentType")
    job.job_type = employment[0] if isinstance(employment, list) and employment else employment
    if posting.get("jobLocationType") == "TELECOMMUTE":
        job.is_remote = True
        job.location = job.location or "Remote"

    salary = posting.get("baseSalary")
    if isinstance(salary, dict):
        value = salary.get("value")
        job.salary_currency = salary.get("currency")
        if isinstance(value, dict):
            job.salary_min = _number(value.get("minValue", value.get("value")))
            job.salary_max = _number(value.get("maxValue", value.get("value")))
            job.salary_period = value.get("unitText")
        else:
            job.salary_min = job.salary_max = _number(value)

    skills = posting.get("skills")
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.split(",") if s.strip()]
    if isinstance(skills, list) and skills:
        job.required_skills = [str(s) for s in skills]

    experience = posting.get("experienceRequirements")
    if isinstance(experience, dict) and _number(experience.get("monthsOfExperience")) is not None:
        job.min_experience_years = _number(experience["monthsOfExperience"]) / 12
    return job


class GenericJsonLdExtractor(BaseExtractor):
    name = "generic"
    label = "Company career page"
    description = ("Official career pages that describe each opening with schema.org JobPosting data, as many do "
                   "for search engines. Also the fallback for pages no other extractor handles.")
    example_seed = "https://careers.example.com/jobs"

    def parse(self, url: str, html: str) -> ExtractionResult:
        soup = soup_of(html)
        jobs = []
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue  # broken JSON-LD on one script does not stop the page
            jobs.extend(_to_raw_job(item, url) for item in _items(data) if _is_job_posting(item))
        return ExtractionResult(jobs=jobs, links=all_links(soup))
