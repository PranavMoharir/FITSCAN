"""Request and response models for /background-jobs (LLD §4.5-4.6, HLD §12.3)."""

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from app.config import check_weight_values, get_settings
from app.models import BackgroundJob
from app.services.redaction import redact_context, redact_params, redact_text

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


# A weight sent by a client: a whole number from 0 to 100. Strict, so 70.5, 70.0, "70" and true are refused.
Weight = Annotated[int, Field(strict=True, ge=0, le=100)]


class MatchWeightsBody(BaseModel):
    """The four weights of a match run (LLD §7.4): whole numbers that add up to exactly 100, never rescaled."""

    model_config = ConfigDict(extra="forbid")

    required: Weight
    nice: Weight
    experience: Weight
    location: Weight

    @model_validator(mode="after")
    def _add_up_to_100(self) -> "MatchWeightsBody":
        check_weight_values((self.required, self.nice, self.experience, self.location))
        return self


class MatchRequest(BaseModel):
    """POST /background-jobs/match. Without weights, the run uses the active weights (GET /matching/weights)."""

    model_config = ConfigDict(extra="forbid")

    weights: MatchWeightsBody | None = None


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


class AcceptedFileInfo(BaseModel):
    index: int = Field(description="0-based position of the file in the request's `files`")
    upload_id: uuid.UUID = Field(description="The file's ID in this job's parameters and log lines")
    size_bytes: int


class RejectedFileInfo(BaseModel):
    index: int = Field(description="0-based position of the file in the request's `files`")
    code: Literal["FILE_TOO_LARGE", "NOT_A_PDF"]
    message: str


class ResumeJobCreated(BackgroundJobCreated):
    """POST /background-jobs/resume (202): the new job plus each file's result (LLD §4.5).

    Files are identified by position and upload ID; original file names are never returned.
    """

    accepted_files: list[AcceptedFileInfo]
    rejected_files: list[RejectedFileInfo]


def public_params(job: BackgroundJob) -> dict[str, Any] | None:
    """The job's parameters as the API shows them (app/services/redaction.py). A resume job shows each
    file's short upload reference and size only, never a name or storage name, even from older rows; a
    crawl's seed URL and allowed domains lose credentials, secret query values and internal hosts."""
    return redact_params(job.type, job.params)


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
        return super().of(job, params=public_params(job), error_message=redact_text(job.error_message), **extra)


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

    @classmethod
    def of(cls, line: Any) -> "LogLine":
        """A stored log line as the API shows it: message and context redacted (app/services/redaction.py)."""
        return cls(log_id=line.log_id, created_at=line.created_at, level=line.level,
                   message=redact_text(line.message) or "", context=redact_context(line.context))


class LogList(BaseModel):
    items: list[LogLine]
    next_after_id: int
