"""Application settings, read from environment variables (HLD §16.3).

Every setting has a matching entry in `.env.example`. Values come from, in order of priority:

1. real environment variables (Docker Compose sets them for the containers);
2. the `.env` file in the repository root (used when running from the virtual environment).

Nothing secret has a default here: `DATABASE_URL` and `REDIS_URL` must be provided.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/app/config.py -> parents[2] is the repository root. Inside the Docker image this
# path does not exist, so the file is simply skipped and only environment variables are used.
ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class MatchWeights(BaseModel):
    """Weights of the four score components (HLD §10). They must add up to 100."""

    required: float
    nice: float
    experience: float
    location: float


def _split_comma_list(value: object) -> object:
    """Turn "a, b,c" into ["a", "b", "c"]; an empty string becomes an empty list."""
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    # Connections
    database_url: str = Field(description="SQLAlchemy URL, e.g. postgresql+psycopg://user:password@host:5432/db")
    redis_url: str = Field(description="Redis URL, used as the Celery broker, e.g. redis://host:6379/0")

    # Frontend <-> API wiring: only these origins may call the API from a browser.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # Resume uploads and PDF checks (LLD §6.2-6.3)
    upload_dir: Path = Path("uploads")
    max_upload_mb: int = Field(default=20, ge=1)
    max_upload_files: int = Field(default=20, ge=1)  # files per upload request
    max_upload_request_mb: int = Field(default=50, ge=2)  # all files of one request together, checked while streaming
    pdf_max_pages: int = Field(default=20, ge=1)  # longer PDFs fail: limits the damage of "PDF bomb" files

    # Crawler (used once the crawler is implemented)
    crawler_user_agent: str = "FITSCAN-JobMatcher/0.1"
    crawler_default_delay_seconds: float = Field(default=1.0, ge=0)
    crawler_max_retries: int = Field(default=3, ge=0)
    crawler_max_pages_limit: int = Field(default=500, ge=1)
    crawler_request_timeout_seconds: float = Field(default=15.0, gt=0)  # per request, and per browser render
    crawler_private_host_allowlist: Annotated[list[str], NoDecode] = []

    # OCR of scanned pages (LLD §6.5)
    ocr_enabled: bool = True
    ocr_language: str = Field(default="eng", pattern=r"^[a-z_]+(\+[a-z_]+)*$")  # Tesseract codes, e.g. "eng+deu"
    ocr_min_text_chars: int = Field(default=25, ge=0)  # a page with fewer characters and an image counts as scanned
    ocr_timeout_seconds: float = Field(default=60.0, gt=0)  # per page

    # Matching (LLD §7.4): weights of the required, nice-to-have, experience and location components
    match_weights: Annotated[MatchWeights, NoDecode] = MatchWeights(required=70, nice=15, experience=10, location=5)

    # Stale background-job detection (LLD §5.8)
    job_heartbeat_timeout_seconds: int = Field(default=600, ge=1)
    job_queued_timeout_seconds: int = Field(default=600, ge=1)

    @model_validator(mode="after")
    def _request_limit_fits_one_file(self) -> "Settings":
        if self.max_upload_request_mb <= self.max_upload_mb:
            raise ValueError("MAX_UPLOAD_REQUEST_MB must be larger than MAX_UPLOAD_MB, "
                             "or a single file of the allowed size could never be uploaded")
        return self

    @field_validator("cors_origins", "crawler_private_host_allowlist", mode="before")
    @classmethod
    def _parse_comma_list(cls, value: object) -> object:
        return _split_comma_list(value)

    @field_validator("match_weights", mode="before")
    @classmethod
    def _parse_match_weights(cls, value: object) -> object:
        """Accept "70,15,10,5" (order: required, nice-to-have, experience, location)."""
        if isinstance(value, str):
            parts = _split_comma_list(value)
            if len(parts) != 4:
                raise ValueError("MATCH_WEIGHTS needs exactly four numbers: required,nice,experience,location")
            numbers = [float(part) for part in parts]
            value = dict(zip(("required", "nice", "experience", "location"), numbers))
        return value

    @field_validator("match_weights")
    @classmethod
    def _check_match_weights(cls, weights: MatchWeights) -> MatchWeights:
        values = (weights.required, weights.nice, weights.experience, weights.location)
        if any(v < 0 for v in values):
            raise ValueError("MATCH_WEIGHTS values must not be negative")
        if abs(sum(values) - 100) > 1e-9:
            raise ValueError("MATCH_WEIGHTS must add up to 100, so scores stay on a 0-100 scale")
        return weights


@lru_cache
def get_settings() -> Settings:
    """Load the settings once and reuse them (FastAPI's recommended pattern)."""
    return Settings()
