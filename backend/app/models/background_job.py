"""`background_jobs` and `background_job_logs` (LLD §3.4, ER diagram 2 of 2)."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, in_values

if TYPE_CHECKING:
    from app.models.candidate import Candidate
    from app.models.job import Job

BACKGROUND_JOB_TYPES = ("crawl", "resume", "match")
BACKGROUND_JOB_STATUSES = ("queued", "running", "completed", "failed", "cancelled")


class BackgroundJob(Base):
    """One row per crawl, resume or match run."""

    __tablename__ = "background_jobs"
    __table_args__ = (
        CheckConstraint(in_values("type", BACKGROUND_JOB_TYPES), name="type"),
        CheckConstraint(in_values("status", BACKGROUND_JOB_STATUSES), name="status"),
        CheckConstraint("progress_current >= 0", name="progress_current_not_negative"),
        Index("ix_background_jobs_status_created_at", "status", "created_at"),
    )

    background_job_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    progress_current: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    progress_total: Mapped[int | None] = mapped_column(Integer)
    items_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    items_failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    error_message: Mapped[str | None] = mapped_column(Text)
    celery_task_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    logs: Mapped[list["BackgroundJobLog"]] = relationship(
        back_populates="background_job",
        cascade="all, delete-orphan",
        passive_deletes=True,  # the database deletes the log lines (ON DELETE CASCADE)
        order_by="BackgroundJobLog.log_id",
    )
    jobs: Mapped[list["Job"]] = relationship(back_populates="background_job")
    candidates: Mapped[list["Candidate"]] = relationship(back_populates="background_job")


class BackgroundJobLog(Base):
    """A timestamped log line. `log_id` always increases, so the UI can ask for lines after N."""

    __tablename__ = "background_job_logs"
    __table_args__ = (Index("ix_background_job_logs_background_job_id_log_id", "background_job_id", "log_id"),)

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)  # BIGSERIAL
    background_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("background_jobs.background_job_id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    level: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))

    background_job: Mapped[BackgroundJob] = relationship(back_populates="logs")
