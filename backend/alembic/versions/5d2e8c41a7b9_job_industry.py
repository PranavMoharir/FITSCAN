"""jobs.industry: the industry of each job posting

Adds `jobs.industry`: text, not null, default 'other' ("Other / Unclassified"), limited to the 13
industry codes by a check constraint, and indexed for the Jobs page filter (LLD §3.3, §5.18).
The Jobs search filters and counts in SQL, page by page, so the industry must be a column.

The jobs that already exist are classified once, with the rules the crawler uses
(`app.industries.classifier`), from their title, description and skills. Only the new column is
written: `updated_at` and every other column keep their values. New and re-crawled jobs get their
industry when they are saved. Downgrade drops the column.

Revision ID: 5d2e8c41a7b9
Revises: 98acdef52211
Create Date: 2026-11-22 21:40:00.000000

"""
from collections import defaultdict
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5d2e8c41a7b9'
down_revision: Union[str, Sequence[str], None] = '98acdef52211'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The industry codes at this revision (app.industries.INDUSTRIES); a later change needs a new migration.
INDUSTRIES = (
    "software_it", "ai_data", "finance_banking", "marketing", "sales_business", "human_resources", "design",
    "operations_supply_chain", "healthcare", "education", "engineering", "legal", "other",
)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('jobs', sa.Column('industry', sa.Text(), server_default=sa.text("'other'"), nullable=False))
    quoted = ", ".join(f"'{code}'" for code in INDUSTRIES)
    op.create_check_constraint(op.f('ck_jobs_industry'), 'jobs', f"industry IN ({quoted})")
    op.create_index('ix_jobs_industry', 'jobs', ['industry'], unique=False)
    _classify_existing_jobs()


def _classify_existing_jobs() -> None:
    """Give every existing job the industry the crawler would give it today (only that column changes)."""
    from app.industries.classifier import classify

    connection = op.get_bind()
    skills: dict = defaultdict(list)
    for job_id, name in connection.execute(sa.text(
            "SELECT js.job_id, s.canonical_name FROM job_skills js JOIN skills s ON s.skill_id = js.skill_id")):
        skills[job_id].append(name)
    updates = []
    for job_id, title, description in connection.execute(sa.text("SELECT job_id, title, description FROM jobs")):
        industry = classify(title, description, skills[job_id]).industry
        if industry != "other":  # 'other' is already the default
            updates.append({"job_id": job_id, "industry": industry})
    if updates:
        connection.execute(sa.text("UPDATE jobs SET industry = :industry WHERE job_id = :job_id"), updates)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_jobs_industry', table_name='jobs')
    op.drop_constraint(op.f('ck_jobs_industry'), 'jobs', type_='check')
    op.drop_column('jobs', 'industry')
