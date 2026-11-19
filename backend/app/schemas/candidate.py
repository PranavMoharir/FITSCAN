"""Candidates: `CandidateRecord` (a parsed resume, validated before it is saved; LLD §6.7, HLD §8.7) and
the search and detail API models (LLD §4.5-4.6).

Email format, numbers as numbers and lists as lists are checked here. `validate_candidate` turns
an invalid **optional** field into null and adds a note to `parse_warnings` ("invalid email
removed"), so a resume with a malformed phone number is still saved. An invalid required field
(for example empty text) means there is no usable candidate.

Pydantic's own error messages include the rejected value, which can be personal data. They are
never logged or returned: `RecordInvalid` names only the fields.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError

from app.schemas.common import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, ExportFormat, Number, SearchText, SortOrder


class EducationEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    degree: str | None = Field(default=None, max_length=200)
    institution: str | None = Field(default=None, max_length=200)
    years: str | None = Field(default=None, max_length=20)  # "2014-2018", "2019-Present" or "2018"


class CandidateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, pattern=r"^\+?\d{8,15}$")  # digits, optional leading +
    city: str | None = Field(default=None, max_length=100)
    current_title: str | None = Field(default=None, max_length=200)
    years_experience: Decimal | None = Field(default=None, ge=0, le=70)
    education: list[EducationEntry] = Field(default_factory=list)
    summary: str | None = Field(default=None, max_length=2000)
    skills: list[str] = Field(default_factory=list)  # canonical names from the taxonomy
    source_file: str = Field(min_length=1, max_length=255)  # original upload name, data only
    parsed_with_ocr: bool
    file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stored_path: str = Field(min_length=1)  # "<upload_id>.pdf" inside UPLOAD_DIR; never returned by the API
    resume_text: str = Field(min_length=1)
    parse_warnings: list[str] = Field(default_factory=list)


OPTIONAL_FIELDS = ("email", "phone", "city", "current_title", "years_experience", "education", "summary")


class RecordInvalid(Exception):
    """A required field is invalid. Carries field names only, never values."""

    def __init__(self, fields: list[str]):
        super().__init__(", ".join(fields))
        self.fields = fields


def validate_candidate(data: dict[str, Any]) -> CandidateRecord:
    data = dict(data)
    warnings = list(data.get("parse_warnings") or [])
    for _ in range(len(OPTIONAL_FIELDS) + 1):  # each round removes at least one invalid field
        try:
            return CandidateRecord(**{**data, "parse_warnings": warnings})
        except ValidationError as exc:
            invalid = sorted({str(error["loc"][0]) for error in exc.errors() if error.get("loc")})
            required = [name for name in invalid if name not in OPTIONAL_FIELDS]
            if required:
                raise RecordInvalid(required) from None
            for name in invalid:
                data[name] = [] if name == "education" else None
                warnings.append(f"invalid {name.replace('_', ' ')} removed")
    raise RecordInvalid(list(OPTIONAL_FIELDS))  # not reached: every optional field accepts null


# --- GET /candidates, GET /candidates/{id}, GET /exports/candidates (LLD §4.4-4.6) -------------------
#
# What the API returns is decided here, field by field. The internal columns (`stored_path`,
# `resume_text`, `file_sha256`, `background_job_id`) are never selected by the search service, so
# they cannot appear in a response or an export.

CandidateSort = Literal["name", "years_experience"]


class CandidateFilterParams(BaseModel):
    """The /candidates filters, shared by the search, the candidate export and the match export (LLD-10)."""

    model_config = ConfigDict(extra="forbid")  # an unknown query parameter is a 422, never silently ignored

    q: SearchText = Field(None, description="Text in the name or the current title (case-insensitive substring)",
                          examples=["developer"])
    skill: SearchText = Field(None, description="A skill or one of its aliases: 'reactjs' finds React",
                              examples=["react"])
    city: SearchText = Field(None, description="The candidate's city; other spellings of a known city also match "
                                               "('bangalore' finds 'Bengaluru')", examples=["pune"])
    sort: CandidateSort = Field("name", description="name (default, A to Z) or years_experience")
    order: SortOrder | None = Field(None, description="asc or desc; default asc for name, desc for years_experience")


class CandidateSearchParams(CandidateFilterParams):
    page: int = Field(1, ge=1)
    page_size: int = Field(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class CandidateExportParams(CandidateFilterParams):
    format: ExportFormat


class CandidateSummary(BaseModel):
    """One item of GET /candidates: the candidate fields of the brief (HLD §12.4, LLD §4.6)."""

    candidate_id: uuid.UUID
    name: str | None
    email: str | None
    phone: str | None
    city: str | None
    current_title: str | None
    skills: list[str]
    years_experience: Number | None
    education: list[EducationEntry]
    summary: str | None
    source_file: str = Field(description="The original upload name, kept as data only")
    parsed_with_ocr: bool


_EXAMPLE_CANDIDATE = {
    "candidate_id": "5b1e9c3a-2d4f-4a6b-8c7d-9e0f1a2b3c4d", "name": "Asha Verma", "email": "asha.verma@example.com",
    "phone": "+919876543210", "city": "Pune", "current_title": "Senior Backend Engineer",
    "skills": ["Docker", "FastAPI", "PostgreSQL", "Python", "Redis"], "years_experience": 6,
    "education": [{"degree": "B.Tech in Computer Engineering", "institution": "Savitribai Phule Pune University",
                   "years": "2013 - 2017"}],
    "summary": "Backend engineer with 6+ years of experience building reliable APIs.",
    "source_file": "asha_verma_cv.pdf", "parsed_with_ocr": False,
}


class CandidateDetail(CandidateSummary):
    """GET /candidates/{id}: the search fields plus the parse warnings (LLD §8.2). Matches: GET /candidates/{id}/matches."""

    model_config = ConfigDict(json_schema_extra={"examples": [{
        **_EXAMPLE_CANDIDATE, "parse_warnings": ["invalid phone removed"],
        "created_at": "2026-11-18T15:02:11Z", "updated_at": "2026-11-19T12:31:40Z"}]})

    parse_warnings: list[str]
    created_at: datetime
    updated_at: datetime


class CandidateList(BaseModel):
    """GET /candidates: one page of candidates in the requested order (LLD §4.4)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "items": [_EXAMPLE_CANDIDATE], "total": 1, "page": 1, "page_size": 20}]})

    items: list[CandidateSummary]
    total: int = Field(description="All candidates that match the filters, on every page")
    page: int
    page_size: int
