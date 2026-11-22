"""From an extractor's RawJob to a saved job (LLD §5.17).

1. Normalize the loose fields (`normalize.py`).
2. Extract canonical skills and split them into required and nice-to-have (`app/skills`).
3. Validate with the Pydantic `JobRecord` schema; an invalid record raises ValidationError.
4. Upsert into `jobs` by `dedup_key` and save the skill links in `job_skills`.

The upsert merges: newer non-empty values overwrite older ones, and empty values never erase
known ones. So a job seen on a listing page and later on its detail page becomes one complete
record (LLD §3.6). Skill links are replaced only when the new record carries skill information
(a description or structured skill lists), so a later listing card cannot erase them.

Each save also says which jobs are new or have changed match inputs (`SaveResult.match_inputs_changed`):
the values matching reads (LLD §7.2) as stored before and after the save. A job that is fetched
again unchanged, or whose only change is a column matching never reads, is not counted. This
drives automatic re-matching after a crawl (LLD §7.1).
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, delete, func, literal_column, or_, select
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
from app.industries.classifier import classify
from app.models import Job, JobSkill, Skill
from app.schemas.job import JobRecord
from app.skills.extractor import extract_job_skills
from app.skills.sync import skill_ids

# Nullable columns merged with COALESCE(new, old): a new value wins, an empty one keeps the old.
_MERGED_COLUMNS = ("company", "location", "salary_min", "salary_max", "salary_currency", "salary_period",
                   "salary_text", "posted_date", "description", "min_experience_years")

# The job columns matching reads (engine.load_inputs), besides the required and nice-to-have skills.
# The description is the job's text for the TF-IDF tie-breaker.
MATCH_INPUT_COLUMNS = ("description", "min_experience_years", "location", "is_remote")


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
    # Jobs saved new, or whose skills, minimum experience, location, remote flag or description changed
    match_inputs_changed: list[uuid.UUID] = field(default_factory=list)

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


def _skill_links(session: Session, job_id: uuid.UUID) -> dict[tuple[int, str], str]:
    """The job's stored skill links: (skill_id, requirement level) -> canonical skill name."""
    rows = session.execute(select(JobSkill.skill_id, JobSkill.requirement_level, Skill.canonical_name)
                           .join(Skill, Skill.skill_id == JobSkill.skill_id).where(JobSkill.job_id == job_id))
    return {(skill_id, level): name for skill_id, level, name in rows}


def save_records(session: Session, records: list[BuiltRecord], background_job_id: uuid.UUID | None) -> SaveResult:
    """Upsert the records and their skill links. The caller commits."""
    result = SaveResult()
    match_columns = [Job.__table__.c[column] for column in MATCH_INPUT_COLUMNS]
    for built in records:
        record = built.record
        # The stored match inputs before this save. FOR UPDATE: a concurrent crawl saving the same
        # job waits for this transaction, so each save compares against the latest committed values.
        before = session.execute(select(Job.job_id, *match_columns).where(Job.dedup_key == record.dedup_key)
                                 .with_for_update()).first()
        stored_links = _skill_links(session, before.job_id) if before else {}
        links_before = set(stored_links)

        # The industry of the job as it will be stored (LLD §5.18): the new title; the new description,
        # or the stored one if this record has none (the merge below keeps it); the new skills if this
        # record carries skill information, otherwise the stored ones.
        description = record.description if record.description is not None else (before.description if before else None)
        skills = (record.required_skills + record.nice_to_have_skills) if built.skills_known else stored_links.values()
        values = record.model_dump(exclude={"required_skills", "nice_to_have_skills"})
        values["industry"] = classify(record.title, description, skills).industry
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
            industry=new.industry,
            job_type=case((new.job_type == "unknown", old.job_type), else_=new.job_type),
            is_remote=or_(old.is_remote, new.is_remote),
            updated_at=func.now(),
        )
        row = session.execute(
            statement.on_conflict_do_update(index_elements=[Job.dedup_key], set_=updates)
            .returning(Job.job_id, literal_column("(xmax = 0)").label("inserted"), *match_columns)
        ).one()
        if row.inserted:
            result.inserted += 1
        else:
            result.updated += 1

        links_after = links_before
        if built.skills_known:
            ids = skill_ids(session, record.required_skills + record.nice_to_have_skills)
            session.execute(delete(JobSkill).where(JobSkill.job_id == row.job_id))
            links = [{"job_id": row.job_id, "skill_id": ids[name], "requirement_level": "required"}
                     for name in record.required_skills]
            links += [{"job_id": row.job_id, "skill_id": ids[name], "requirement_level": "nice_to_have"}
                      for name in record.nice_to_have_skills]
            if links:
                session.execute(insert(JobSkill).values(links))
            links_after = {(link["skill_id"], link["requirement_level"]) for link in links}

        # New (or saved by a concurrent crawl after the check above), or a match input changed.
        if (row.inserted or before is None or tuple(before[1:]) != tuple(row[2:])
                or links_after != links_before):
            result.match_inputs_changed.append(row.job_id)
    return result
