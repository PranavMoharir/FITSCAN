"""Reclassify the industry of stored jobs with the current rules (LLD §5.18). A dry run unless --apply.

New and re-crawled jobs get their industry when they are saved. After the rules change
(app/industries/industries.json), this brings the jobs already stored up to date without a crawl:

    python -m app.services.reclassify            # list what would change; writes nothing
    python -m app.services.reclassify --apply    # write the changes

Only `jobs.industry` is written: `updated_at` and every other column keep their values. Run it in
the `api` container (`docker compose exec api python -m app.services.reclassify`).
"""

import argparse
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.industries.classifier import classify
from app.models import Job, JobSkill, Skill


@dataclass(frozen=True)
class Change:
    job_id: uuid.UUID
    title: str
    old: str
    new: str


def find_changes(session: Session) -> list[Change]:
    """Every job whose stored industry differs from what the current rules give."""
    skills: dict[uuid.UUID, list[str]] = defaultdict(list)
    for job_id, name in session.execute(select(JobSkill.job_id, Skill.canonical_name).join(Skill)):
        skills[job_id].append(name)
    changes = []
    for job_id, title, description, industry in session.execute(
            select(Job.job_id, Job.title, Job.description, Job.industry).order_by(Job.title, Job.job_id)):
        new = classify(title, description, skills[job_id]).industry
        if new != industry:
            changes.append(Change(job_id, title, industry, new))
    return changes


def apply_changes(session: Session, changes: list[Change]) -> None:
    """Write the new industries; updated_at is set to itself, so the column's on-update default does not fire."""
    for change in changes:
        session.execute(update(Job).where(Job.job_id == change.job_id)
                        .values(industry=change.new, updated_at=Job.updated_at))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reclassify the industry of stored jobs with the current rules.")
    parser.add_argument("--apply", action="store_true", help="write the changes (default: only list them)")
    args = parser.parse_args(argv)
    with SessionLocal() as session:
        changes = find_changes(session)
        for change in changes:
            print(f"{change.job_id}  {change.old} -> {change.new}  {change.title}")
        if args.apply and changes:
            apply_changes(session, changes)
            session.commit()
        action = "Changed" if args.apply else "Would change"
        print(f"{action} the industry of {len(changes)} jobs." + ("" if args.apply else " Run with --apply to write it."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
