"""`CandidateRecord`: a parsed resume, validated before it is saved (LLD §6.7, HLD §8.7).

Email format, numbers as numbers and lists as lists are checked here. `validate_candidate` turns
an invalid **optional** field into null and adds a note to `parse_warnings` ("invalid email
removed"), so a resume with a malformed phone number is still saved. An invalid required field
(for example empty text) means there is no usable candidate.

Pydantic's own error messages include the rejected value, which can be personal data. They are
never logged or returned: `RecordInvalid` names only the fields.
"""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError


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
