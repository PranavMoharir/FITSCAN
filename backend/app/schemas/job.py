"""`JobRecord`: the validated, normalized job that the crawler saves (LLD §5.17 step 4, HLD §11.8).

Numbers are numbers, dates are ISO dates, URLs are absolute http(s) URLs and skills are
canonical names. A record that fails validation is logged and skipped; it is never saved.
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, field_validator, model_validator

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
