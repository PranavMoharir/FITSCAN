"""`candidates` and `candidate_skills` (LLD §3.3, ER diagrams 1 and 2).

A candidate's `skills` are not a column: they are the `candidate_skills` rows.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.background_job import BackgroundJob
    from app.models.match import Match
    from app.models.skill import Skill


class Candidate(Base):
    """One row per parsed resume."""

    __tablename__ = "candidates"
    __table_args__ = (
        CheckConstraint("years_experience >= 0", name="years_experience_not_negative"),
        # Same person, new file: at most one candidate per email address, ignoring case (LLD §3.6).
        Index("uq_candidates_lower_email", text("lower(email)"), unique=True, postgresql_where=text("email IS NOT NULL")),
        Index("ix_candidates_city", "city"),
        Index("ix_candidates_name_trgm", "name", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}),
        Index(
            "ix_candidates_current_title_trgm",
            "current_title",
            postgresql_using="gin",
            postgresql_ops={"current_title": "gin_trgm_ops"},
        ),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    current_title: Mapped[str | None] = mapped_column(Text)
    years_experience: Mapped[Decimal | None] = mapped_column(Numeric)
    education: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB(none_as_null=True))
    summary: Mapped[str | None] = mapped_column(Text)
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_with_ocr: Mapped[bool] = mapped_column(Boolean, nullable=False)
    file_sha256: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    stored_path: Mapped[str | None] = mapped_column(Text)  # internal; never returned by the API
    resume_text: Mapped[str | None] = mapped_column(Text)
    parse_warnings: Mapped[list[str] | None] = mapped_column(JSONB(none_as_null=True))
    background_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("background_jobs.background_job_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    background_job: Mapped["BackgroundJob | None"] = relationship(back_populates="candidates")
    skills: Mapped[list["CandidateSkill"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True
    )
    matches: Mapped[list["Match"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True
    )


class CandidateSkill(Base):
    """Links a candidate to a skill."""

    __tablename__ = "candidate_skills"
    __table_args__ = (Index("ix_candidate_skills_skill_id", "skill_id"),)

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.candidate_id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.skill_id"), primary_key=True)

    candidate: Mapped[Candidate] = relationship(back_populates="skills")
    skill: Mapped["Skill"] = relationship()
