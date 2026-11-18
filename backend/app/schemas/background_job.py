"""Request and response models for /background-jobs (LLD §4.5-4.6, HLD §12.3)."""

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.config import get_settings
from app.models import BackgroundJob

MAX_DEPTH_LIMIT = 10
MAX_ALLOWED_DOMAINS = 20
_HOSTNAME = re.compile(r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$")

BackgroundJobType = Literal["crawl", "resume", "match"]
BackgroundJobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class CrawlRequest(BaseModel):
    """POST /background-jobs/crawl (LLD §5.9)."""

    model_config = ConfigDict(extra="forbid")

    seed_url: HttpUrl
    max_depth: int = Field(ge=1, le=MAX_DEPTH_LIMIT)
    max_pages: int = Field(ge=1)
    allowed_domains: list[str] | None = Field(default=None, min_length=1, max_length=MAX_ALLOWED_DOMAINS)
    extractor: str | None = None

    @field_validator("max_pages")
    @classmethod
    def _within_configured_limit(cls, value: int) -> int:
        limit = get_settings().crawler_max_pages_limit
        if value > limit:
            raise ValueError(f"must be at most {limit} (CRAWLER_MAX_PAGES_LIMIT)")
        return value

    @field_validator("allowed_domains")
    @classmethod
    def _host_names(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = []
        for domain in value:
            host = domain.strip().lower().rstrip(".")
            if not _HOSTNAME.match(host):
                raise ValueError(f"{domain!r} is not a host name (write 'example.com', without http:// or a path)")
            cleaned.append(host)
        return sorted(set(cleaned))


class Progress(BaseModel):
    current: int
    total: int | None
    percent: int


def progress_of(job: BackgroundJob) -> Progress:
    total = job.progress_total
    percent = min(100, job.progress_current * 100 // total) if total else 0
    return Progress(current=job.progress_current, total=total, percent=percent)


class BackgroundJobCreated(BaseModel):
    """Returned by the create endpoints (202 Accepted)."""

    background_job_id: uuid.UUID
    type: BackgroundJobType
    status: BackgroundJobStatus
    progress: Progress
    created_at: datetime

    @classmethod
    def of(cls, job: BackgroundJob, **extra: Any):
        return cls(
            background_job_id=job.background_job_id, type=job.type, status=job.status,
            progress=progress_of(job), created_at=job.created_at, **extra,
        )


class BackgroundJobSummary(BackgroundJobCreated):
    """One item of GET /background-jobs."""

    items_succeeded: int
    items_failed: int
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def of(cls, job: BackgroundJob, **extra: Any):
        return super().of(
            job, items_succeeded=job.items_succeeded, items_failed=job.items_failed,
            started_at=job.started_at, finished_at=job.finished_at, **extra,
        )


class BackgroundJobDetail(BackgroundJobSummary):
    """GET /background-jobs/{id}: also the parameters and, for a failed job, the reason."""

    params: dict[str, Any] | None
    error_message: str | None

    @classmethod
    def of(cls, job: BackgroundJob, **extra: Any):
        return super().of(job, params=job.params, error_message=job.error_message, **extra)


class BackgroundJobList(BaseModel):
    items: list[BackgroundJobSummary]
    total: int
    page: int
    page_size: int


class CancelResult(BaseModel):
    status: BackgroundJobStatus
    cancel_requested: bool | None = None


class LogLine(BaseModel):
    log_id: int
    created_at: datetime
    level: LogLevel
    message: str
    context: dict[str, Any] | None = None


class LogList(BaseModel):
    items: list[LogLine]
    next_after_id: int
