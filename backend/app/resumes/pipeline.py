"""From a stored PDF to a saved candidate (LLD §6.1, §6.7, §3.6).

`parse_resume` (no database access):
    open the PDF (validation.py) -> text, tables and OCR (text_extraction.py, ocr.py)
    -> fields and skills (fields.py) -> CandidateRecord (schemas/candidate.py)

`save_candidate` applies the duplicate rules:
    - the same file (same SHA-256 of its bytes) is a duplicate: nothing is saved;
    - the same email, ignoring case, is the same person: the newer resume replaces the parsed fields;
    - anything else is a new candidate.
Skills are saved as `candidate_skills` rows.

Every message raised here (`FileFailed`) is safe to log: it never contains resume content,
names, contact details or the original file name.
"""

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Candidate, CandidateSkill
from app.resumes.fields import extract_fields
from app.resumes.text_extraction import OcrSettings, PageEvent, extract_text
from app.resumes.validation import PdfFileError, open_pdf
from app.schemas.candidate import CandidateRecord, RecordInvalid, validate_candidate
from app.skills.sync import skill_ids

MIN_RESUME_LETTERS = 50  # less text than this is not a usable resume: no candidate is created


class FileFailed(Exception):
    """The file gives no candidate. `level` is ERROR, or WARNING when a scanned resume is flagged."""

    def __init__(self, message: str, level: str = "ERROR", events: list[PageEvent] | None = None):
        super().__init__(message)
        self.message = message
        self.level = level
        self.events = events or []


@dataclass
class ParsedResume:
    record: CandidateRecord
    pages: int
    ocr_pages: list[int]
    events: list[PageEvent] = field(default_factory=list)  # per-page notes for the job log
    unmatched_terms: list[str] = field(default_factory=list)


@dataclass
class SaveOutcome:
    action: str  # "created", "updated" or "duplicate"
    candidate_id: uuid.UUID


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ocr_settings(settings: Settings) -> OcrSettings:
    return OcrSettings(enabled=settings.ocr_enabled, language=settings.ocr_language,
                       min_text_chars=settings.ocr_min_text_chars, timeout_seconds=settings.ocr_timeout_seconds)


def parse_resume(path: Path, *, source_file: str, sha256: str, stored_path: str, settings: Settings, today: date,
                 on_page: Callable[[int], None] | None = None) -> ParsedResume:
    """Read one stored PDF into a validated CandidateRecord. Raises FileFailed if there is no candidate."""
    try:
        document = open_pdf(path, settings.pdf_max_pages)
    except PdfFileError as exc:
        raise FileFailed(exc.message) from None
    with document:
        pages = document.page_count
        extracted = extract_text(document, path, ocr_settings(settings), on_page=on_page)

    text = extracted.text
    if sum(ch.isalpha() for ch in text) < MIN_RESUME_LETTERS:
        if extracted.unread_scanned_pages:
            raise FileFailed("scanned resume: OCR produced no text, so no candidate was created.",
                             level="WARNING", events=extracted.events)
        raise FileFailed("no usable text could be extracted, so no candidate was created.", events=extracted.events)

    fields = extract_fields(extracted, source_file=source_file, today=today)
    page_warnings = [event.message.rstrip(".") for event in extracted.events if event.level == "WARNING"]
    try:
        record = validate_candidate({
            "name": fields.name, "email": fields.email, "phone": fields.phone, "city": fields.city,
            "current_title": fields.current_title, "years_experience": fields.years_experience,
            "education": fields.education, "summary": fields.summary, "skills": fields.skills,
            "source_file": source_file, "parsed_with_ocr": bool(extracted.ocr_pages), "file_sha256": sha256,
            "stored_path": stored_path, "resume_text": text, "parse_warnings": fields.warnings + page_warnings,
        })
    except RecordInvalid as exc:
        raise FileFailed(f"the parsed data is not valid ({', '.join(exc.fields)}).", events=extracted.events) from None
    return ParsedResume(record, pages, extracted.ocr_pages, extracted.events, fields.unmatched_terms)


# --- Saving -----------------------------------------------------------------------------------------


def find_by_file(session: Session, sha256: str) -> uuid.UUID | None:
    return session.scalar(select(Candidate.candidate_id).where(Candidate.file_sha256 == sha256))


def _values(record: CandidateRecord, job_id: uuid.UUID | None) -> dict:
    data = record.model_dump(mode="python", exclude={"skills"})
    data["email"] = str(record.email) if record.email else None
    data["education"] = [entry.model_dump() for entry in record.education]
    data["background_job_id"] = job_id
    return data


def _replace_skills(session: Session, candidate_id: uuid.UUID, names: list[str]) -> None:
    session.execute(delete(CandidateSkill).where(CandidateSkill.candidate_id == candidate_id))
    ids = skill_ids(session, names)
    if ids:
        session.execute(insert(CandidateSkill), [{"candidate_id": candidate_id, "skill_id": i} for i in ids.values()])


def save_candidate(session: Session, record: CandidateRecord, job_id: uuid.UUID | None, *,
                   retry: bool = True) -> SaveOutcome:
    """Insert, update (same email) or skip (same file) one candidate, with its skills."""
    existing = find_by_file(session, record.file_sha256)
    if existing is not None:
        return SaveOutcome("duplicate", existing)

    values = _values(record, job_id)
    if record.email:
        same_person = session.scalar(
            select(Candidate).where(func.lower(Candidate.email) == str(record.email).lower()).with_for_update()
        )
        if same_person is not None:
            for column, value in values.items():  # the newer resume replaces the parsed fields
                setattr(same_person, column, value)
            session.flush()
            _replace_skills(session, same_person.candidate_id, record.skills)
            return SaveOutcome("updated", same_person.candidate_id)

    candidate = Candidate(**values)
    try:
        with session.begin_nested():
            session.add(candidate)
            session.flush()
    except IntegrityError:
        # Another job saved the same file or email a moment ago: apply the rules once more.
        if retry:
            return save_candidate(session, record, job_id, retry=False)
        raise
    _replace_skills(session, candidate.candidate_id, record.skills)
    return SaveOutcome("created", candidate.candidate_id)
