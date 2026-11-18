"""`matches`: one row per (candidate, job) pair (LLD §3.3, ER diagram 1 of 2).

`score` is DOUBLE PRECISION and is stored at full precision. It is rounded to 2 decimals
only for display, so rounding can never change the ranking (ADR-017, HLD §10.5).

All JSONB columns in the models use `none_as_null=True`: Python `None` is stored as SQL NULL,
not as the JSON value `null`, so NOT NULL constraints and `IS NULL` checks work as expected.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, Double, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.candidate import Candidate
    from app.models.job import Job


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (CheckConstraint("score >= 0 AND score <= 100", name="score_range"),)

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.candidate_id", ondelete="CASCADE"), primary_key=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.job_id", ondelete="CASCADE"), primary_key=True)
    score: Mapped[float] = mapped_column(Double, nullable=False)  # DOUBLE PRECISION, never rounded in storage
    matched_skills: Mapped[list[dict[str, Any]]] = mapped_column(JSONB(none_as_null=True), nullable=False)
    missing_skills: Mapped[list[dict[str, Any]]] = mapped_column(JSONB(none_as_null=True), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB(none_as_null=True), nullable=False)
    text_similarity: Mapped[float | None] = mapped_column(Double)  # TF-IDF tie-breaker, full precision
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    candidate: Mapped["Candidate"] = relationship(back_populates="matches")
    job: Mapped["Job"] = relationship(back_populates="matches")


# Top 10 jobs for a candidate, and top 10 candidates for a job (LLD §3.7).
Index("ix_matches_candidate_id_score", Match.candidate_id, Match.score.desc())
Index("ix_matches_job_id_score", Match.job_id, Match.score.desc())
