"""`jobs` and `job_skills` (LLD §3.3, ER diagrams 1 and 2).

`required_skills` and `nice_to_have_skills` are not columns: they are the `job_skills`
rows with requirement_level `required` or `nice_to_have`.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, Text, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, in_values

if TYPE_CHECKING:
    from app.models.background_job import BackgroundJob
    from app.models.match import Match
    from app.models.skill import Skill

JOB_TYPES = ("full_time", "part_time", "contract", "internship", "temporary", "unknown")
REQUIREMENT_LEVELS = ("required", "nice_to_have")


class Job(Base):
    """One row per job posting."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(in_values("job_type", JOB_TYPES), name="job_type"),
        CheckConstraint("salary_min <= salary_max", name="salary_range"),  # passes when either is NULL
        CheckConstraint("min_experience_years >= 0", name="min_experience_years_not_negative"),
        Index("ix_jobs_posted_date", "posted_date"),
        Index("ix_jobs_location", "location"),
        Index("ix_jobs_title_trgm", "title", postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"}),
        Index("ix_jobs_company_trgm", "company", postgresql_using="gin", postgresql_ops={"company": "gin_trgm_ops"}),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    job_type: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'unknown'"))
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric)
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric)
    salary_currency: Mapped[str | None] = mapped_column(Text)
    salary_period: Mapped[str | None] = mapped_column(Text)
    salary_text: Mapped[str | None] = mapped_column(Text)
    posted_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    min_experience_years: Mapped[Decimal | None] = mapped_column(Numeric)
    apply_url: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    is_remote: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    source_url: Mapped[str | None] = mapped_column(Text)
    dedup_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    background_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("background_jobs.background_job_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    background_job: Mapped["BackgroundJob | None"] = relationship(back_populates="jobs")
    skills: Mapped[list["JobSkill"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", passive_deletes=True
    )
    matches: Mapped[list["Match"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", passive_deletes=True
    )


class JobSkill(Base):
    """Links a job to a skill, as required or nice-to-have."""

    __tablename__ = "job_skills"
    __table_args__ = (
        CheckConstraint(in_values("requirement_level", REQUIREMENT_LEVELS), name="requirement_level"),
        Index("ix_job_skills_skill_id", "skill_id"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.job_id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.skill_id"), primary_key=True)
    requirement_level: Mapped[str] = mapped_column(Text, nullable=False)

    job: Mapped[Job] = relationship(back_populates="skills")
    skill: Mapped["Skill"] = relationship()
