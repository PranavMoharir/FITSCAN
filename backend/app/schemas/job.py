"""Jobs: `JobRecord` (what the crawler saves) and the search and detail API models (LLD §4.5-4.6).

`JobRecord` is the validated, normalized job that the crawler saves (LLD §5.17 step 4, HLD §11.8).
Numbers are numbers, dates are ISO dates, URLs are absolute http(s) URLs and skills are
canonical names. A record that fails validation is logged and skipped; it is never saved.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, field_validator, model_validator

from app.schemas.common import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, ExportFormat, Number, SearchText, SortOrder

JobType = Literal["full_time", "part_time", "contract", "internship", "temporary", "unknown"]
SalaryPeriod = Literal["year", "month", "week", "day", "hour"]
_HTTP_URL = TypeAdapter(HttpUrl)


class JobRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    company: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=300)
    job_type: JobType = "unknown"
    salary_min: Decimal | None = Field(default=None, ge=0)
    salary_max: Decimal | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    salary_period: SalaryPeriod | None = None
    salary_text: str | None = Field(default=None, max_length=300)
    posted_date: date | None = None
    description: str | None = Field(default=None, max_length=100_000)
    min_experience_years: Decimal | None = Field(default=None, ge=0, le=50)
    apply_url: str
    source: str = Field(min_length=1, max_length=100)
    is_remote: bool = False
    source_url: str
    dedup_key: str = Field(min_length=1, max_length=2048)
    required_skills: list[str] = []
    nice_to_have_skills: list[str] = []

    @field_validator("apply_url", "source_url")
    @classmethod
    def _absolute_http_url(cls, value: str) -> str:
        url = _HTTP_URL.validate_python(value)  # raises for relative or non-http(s) URLs
        if url.scheme not in ("http", "https"):
            raise ValueError("must be an http or https URL")
        return value

    @model_validator(mode="after")
    def _consistent(self) -> "JobRecord":
        if self.salary_min is not None and self.salary_max is not None and self.salary_min > self.salary_max:
            raise ValueError("salary_min is larger than salary_max")
        both = set(self.required_skills) & set(self.nice_to_have_skills)
        if both:
            raise ValueError(f"skills listed as both required and nice-to-have: {sorted(both)}")
        return self


# --- GET /jobs, GET /jobs/{id}, GET /exports/jobs (LLD §4.4-4.6) -------------------------------------

JobSort = Literal["posted_date", "title"]


class JobFilterParams(BaseModel):
    """The /jobs filters, shared by the search and the export (HLD §9.4: what you see is what you export)."""

    model_config = ConfigDict(extra="forbid")  # an unknown query parameter is a 422, never silently ignored

    q: SearchText = Field(None, description="Text in the title or the company (case-insensitive substring)",
                          examples=["python"])
    skill: SearchText = Field(None, description="A skill or one of its aliases, at either level: 'js' finds JavaScript",
                              examples=["js"])
    location: SearchText = Field(None, description="Text in the location; a known city also matches its other "
                                                   "spellings ('bangalore' finds 'Bengaluru')", examples=["pune"])
    job_type: JobType | None = None
    max_required_years: Decimal | None = Field(
        None, ge=0, le=50, description="Jobs asking for at most this many years, plus jobs with no minimum (LLD-6)",
        examples=[3])
    sort: JobSort = Field("posted_date", description="posted_date (default, newest first) or title")
    order: SortOrder | None = Field(None, description="asc or desc; default desc for posted_date, asc for title")


class JobSearchParams(JobFilterParams):
    page: int = Field(1, ge=1)
    page_size: int = Field(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class JobExportParams(JobFilterParams):
    format: ExportFormat


class Salary(BaseModel):
    min: Number | None
    max: Number | None
    currency: str | None
    period: str | None


class JobSummary(BaseModel):
    """One item of GET /jobs (the fields of HLD §12.4)."""

    job_id: uuid.UUID
    title: str
    company: str | None
    location: str | None
    job_type: JobType
    salary: Salary | None = Field(description="null when the posting gives no salary numbers, currency or period")
    posted_date: date | None
    required_skills: list[str]
    nice_to_have_skills: list[str]
    min_experience_years: Number | None
    apply_url: str
    source: str


class JobDetail(JobSummary):
    """GET /jobs/{id}: every stored field of the job. Its matches come from GET /jobs/{id}/matches."""

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "job_id": "a91c5d2e-0f7b-4f3a-9d1e-2b8c7a6e5f40", "title": "Backend Python Developer",
        "company": "Acme Analytics", "location": "Pune, India", "job_type": "full_time",
        "salary": {"min": 900000, "max": 1400000, "currency": "INR", "period": "year"}, "posted_date": "2026-11-03",
        "required_skills": ["Django", "FastAPI", "PostgreSQL", "Pytest", "Python"],
        "nice_to_have_skills": ["Docker", "Kubernetes", "Redis"], "min_experience_years": 3,
        "apply_url": "http://mock-site:8080/static/jobs/backend-python-developer.html", "source": "mock_static",
        "is_remote": False, "description": "We build APIs with FastAPI and PostgreSQL. 3+ years of experience.",
        "salary_text": "₹9,00,000 – ₹14,00,000 a year",
        "source_url": "http://mock-site:8080/static/jobs/backend-python-developer.html",
        "created_at": "2026-11-18T14:22:50Z", "updated_at": "2026-11-19T11:59:00Z"}]})

    is_remote: bool
    description: str | None
    salary_text: str | None
    source_url: str | None
    created_at: datetime
    updated_at: datetime


class JobList(BaseModel):
    """GET /jobs: one page of jobs in the requested order (LLD §4.4)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "items": [{"job_id": "a91c5d2e-0f7b-4f3a-9d1e-2b8c7a6e5f40", "title": "Backend Python Developer",
                   "company": "Acme Analytics", "location": "Pune, India", "job_type": "full_time",
                   "salary": {"min": 900000, "max": 1400000, "currency": "INR", "period": "year"},
                   "posted_date": "2026-11-03", "required_skills": ["Django", "FastAPI", "PostgreSQL", "Pytest", "Python"],
                   "nice_to_have_skills": ["Docker", "Kubernetes", "Redis"], "min_experience_years": 3,
                   "apply_url": "http://mock-site:8080/static/jobs/backend-python-developer.html",
                   "source": "mock_static"}],
        "total": 1, "page": 1, "page_size": 20}]})

    items: list[JobSummary]
    total: int = Field(description="All jobs that match the filters, on every page")
    page: int
    page_size: int
