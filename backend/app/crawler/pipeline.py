"""From an extractor's RawJob to a saved job (LLD §5.17).

1. Normalize the loose fields (`normalize.py`).
2. Extract canonical skills and split them into required and nice-to-have (`app/skills`).
3. Validate with the Pydantic `JobRecord` schema; an invalid record raises ValidationError.
4. Upsert into `jobs` by `dedup_key` and save the skill links in `job_skills`.

The upsert merges: newer non-empty values overwrite older ones, and empty values never erase
known ones. So a job seen on a listing page and later on its detail page becomes one complete
record (LLD §3.6). Skill links are replaced only when the new record carries skill information
(a description or structured skill lists), so a later listing card cannot erase them.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, delete, func, literal_column, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.crawler.normalize import (
    clean_description,
    detect_remote,
    extract_min_experience,
    make_dedup_key,
    map_job_type,
    normalize_period,
    parse_posted_date,
    parse_salary,
    squash,
)
from app.crawler.urls import normalize_url
from app.extractors.base import RawJob
from app.models import Job, JobSkill
from app.schemas.job import JobRecord
from app.skills.extractor import extract_job_skills
from app.skills.sync import skill_ids

# Nullable columns merged with COALESCE(new, old): a new value wins, an empty one keeps the old.
_MERGED_COLUMNS = ("company", "location", "salary_min", "salary_max", "salary_currency", "salary_period",
                   "salary_text", "posted_date", "description", "min_experience_years")


@dataclass
class BuiltRecord:
    record: JobRecord
    skills_known: bool                      # the record carries skill information
    unmatched_terms: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SaveResult:
    inserted: int = 0
    updated: int = 0

    @property
    def saved(self) -> int:
        return self.inserted + self.updated


def _decimal(value: float | Decimal | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def build_record(raw: RawJob, *, page_url: str, source: str, fetched_at: datetime) -> BuiltRecord:
    """Normalize, extract skills and validate. Raises pydantic.ValidationError if invalid."""
    warnings: list[str] = []
    title, company, location = squash(raw.title), squash(raw.company), squash(raw.location)
    # The apply URL must be absolute http(s); a job without one is applied for on its own page.
    apply_url = (normalize_url(raw.apply_url, base=page_url) if raw.apply_url else None) or page_url
    description = clean_description(raw.description)

    if raw.salary_min is not None or raw.salary_max is not None:
        salary_min, salary_max = _decimal(raw.salary_min), _decimal(raw.salary_max)
        currency, period = (raw.salary_currency or "").upper() or None, normalize_period(raw.salary_period)
    else:
        parsed = parse_salary(raw.salary_text)
        salary_min, salary_max, currency, period = parsed.min, parsed.max, parsed.currency, parsed.period

    posted_date = parse_posted_date(raw.posted_date, fetched_at)
    if raw.posted_date and posted_date is None:
        warnings.append(f"unrecognized posted date {squash(raw.posted_date)!r}")

    skills = extract_job_skills(description, raw.required_skills, raw.nice_to_have_skills)
    record = JobRecord(
        title=title or "",
        company=company,
        location=location,
        job_type=map_job_type(raw.job_type),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=currency,
        salary_period=period,
        salary_text=squash(raw.salary_text),
        posted_date=posted_date,
        description=description,
        min_experience_years=_decimal(raw.min_experience_years) if raw.min_experience_years is not None
        else extract_min_experience(description),
        apply_url=apply_url,
        source=source,
        is_remote=bool(raw.is_remote) or detect_remote(location, title),
        source_url=page_url,
        dedup_key=make_dedup_key(apply_url, source, title, company, location),
        required_skills=skills.required,
        nice_to_have_skills=skills.nice_to_have,
    )
    skills_known = description is not None or bool(raw.required_skills or raw.nice_to_have_skills)
    return BuiltRecord(record, skills_known, skills.unmatched, warnings)


def save_records(session: Session, records: list[BuiltRecord], background_job_id: uuid.UUID | None) -> SaveResult:
    """Upsert the records and their skill links. The caller commits."""
    result = SaveResult()
    for built in records:
        record = built.record
        values = record.model_dump(exclude={"required_skills", "nice_to_have_skills"})
        statement = insert(Job).values(job_id=uuid.uuid4(), background_job_id=background_job_id, **values)
        new = statement.excluded
        old = Job.__table__.c
        updates = {column: func.coalesce(new[column], old[column]) for column in _MERGED_COLUMNS}
        updates.update(
            title=new.title,
            apply_url=new.apply_url,
            source=new.source,
            source_url=new.source_url,
            background_job_id=new.background_job_id,
            job_type=case((new.job_type == "unknown", old.job_type), else_=new.job_type),
            is_remote=or_(old.is_remote, new.is_remote),
            updated_at=func.now(),
        )
        row = session.execute(
            statement.on_conflict_do_update(index_elements=[Job.dedup_key], set_=updates)
            .returning(Job.job_id, literal_column("(xmax = 0)").label("inserted"))
        ).one()
        if row.inserted:
            result.inserted += 1
        else:
            result.updated += 1

        if built.skills_known:
            ids = skill_ids(session, record.required_skills + record.nice_to_have_skills)
            session.execute(delete(JobSkill).where(JobSkill.job_id == row.job_id))
            links = [{"job_id": row.job_id, "skill_id": ids[name], "requirement_level": "required"}
                     for name in record.required_skills]
            links += [{"job_id": row.job_id, "skill_id": ids[name], "requirement_level": "nice_to_have"}
                      for name in record.nice_to_have_skills]
            if links:
                session.execute(insert(JobSkill).values(links))
    return result
