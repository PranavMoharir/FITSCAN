"""Upload checks (API) and PDF opening checks (worker) (LLD §6.2, §6.3).

API side, for each uploaded file (`save_upload`):

1. The declared extension and content type must not say "this is something else" (for example
   `notes.txt` or `text/plain`). They are checked, but never trusted on their own.
2. The first bytes must be the PDF signature `%PDF-`.
3. The size is counted while the file is copied in chunks, so an oversized file is never read
   into memory as a whole, and copying stops as soon as the limit is passed.

An accepted file is stored as `<upload_id>.pdf`, where `upload_id` is a random UUID. The original
file name is never part of a path, which prevents path traversal. It travels to the worker in a
small metadata file next to the PDF, `<upload_id>.json`, on the same uploads volume (which no
endpoint serves). So the name is never in the job's parameters, an API response, Redis or a log
line; after parsing it is kept only as `candidates.source_file`. Responses identify a file by its
position in the request (`index`) and its `upload_id`; logs by its `upload_id`.

Worker side (`open_pdf`): PyMuPDF opens the stored file. A file that cannot be opened is corrupt,
one that needs a password is encrypted, and one with too many pages is refused. The messages
contain no file content. PyMuPDF is imported inside `open_pdf` only, because the API image does
not install it.
"""

import json
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import BinaryIO

PDF_SIGNATURE = b"%PDF-"
CHUNK_BYTES = 64 * 1024
MAX_NAME_CHARS = 255
# Browsers send application/pdf. curl, scripts and some browsers send a generic binary type,
# so those are allowed too: the signature check decides.
PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf", "application/acrobat",
                     "application/octet-stream", "binary/octet-stream"}
NOT_A_PDF_MESSAGE = "File is not a PDF document."


@dataclass(frozen=True)
class IncomingFile:
    """One uploaded file as the router hands it over (no FastAPI types in domain code)."""

    stream: BinaryIO
    filename: str | None
    content_type: str | None


@dataclass(frozen=True)
class AcceptedFile:
    index: int      # 0-based position of the file in the request: how the client recognises it
    upload_id: str  # random UUID: the stored file name and the file's ID in logs
    file: str       # original name: written to the metadata file only, never returned or logged
    size_bytes: int


@dataclass(frozen=True)
class RejectedFile:
    index: int
    code: str  # FILE_TOO_LARGE or NOT_A_PDF (LLD §4.5)
    message: str  # never contains the file name


class PdfFileError(Exception):
    """A stored file that cannot be processed. The message is safe to log: it has no file content."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def display_name(raw: str | None) -> str:
    """The original file name as data: no folders, no control characters, bounded length."""
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    return name[:MAX_NAME_CHARS] or "unnamed.pdf"


def stored_name(upload_id: str) -> str:
    """`<uuid>.pdf`. Parsing the ID as a UUID guarantees the name has no path characters."""
    return f"{uuid.UUID(upload_id)}.pdf"


def metadata_name(upload_id: str) -> str:
    """`<uuid>.json`: the original file name, for the worker (never a path, never logged)."""
    return f"{uuid.UUID(upload_id)}.json"


def _write_metadata(upload_dir: Path, upload_id: str, source_file: str) -> None:
    partial = upload_dir / f"{upload_id}.json.part"
    partial.write_text(json.dumps({"source_file": source_file}), encoding="utf-8")
    partial.replace(upload_dir / metadata_name(upload_id))


def read_source_file(upload_dir: Path, upload_id: str) -> str | None:
    """The original file name stored with an upload, or None if its metadata file is missing or broken."""
    try:
        data = json.loads((upload_dir / metadata_name(upload_id)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    name = data.get("source_file") if isinstance(data, dict) else None
    return display_name(name) if isinstance(name, str) and name else None


def _declared_as_something_else(name: str, content_type: str | None) -> bool:
    suffix = PurePath(name).suffix.lower()
    if suffix and suffix != ".pdf":
        return True
    media_type = (content_type or "").split(";")[0].strip().lower()
    return bool(media_type) and media_type not in PDF_CONTENT_TYPES


def save_upload(stream: BinaryIO, raw_name: str | None, content_type: str | None, upload_dir: Path,
                max_bytes: int, index: int = 0) -> AcceptedFile | RejectedFile:
    """Check one uploaded file and, if it passes, store it as `<upload_id>.pdf` in `upload_dir`.

    `index` is the file's position in the request; results refer to the file by it, not by name.
    """
    name = display_name(raw_name)
    if _declared_as_something_else(name, content_type):
        return RejectedFile(index, "NOT_A_PDF", NOT_A_PDF_MESSAGE)
    chunk = stream.read(CHUNK_BYTES)
    if not chunk.startswith(PDF_SIGNATURE):
        return RejectedFile(index, "NOT_A_PDF", NOT_A_PDF_MESSAGE)

    upload_id = str(uuid.uuid4())
    upload_dir.mkdir(parents=True, exist_ok=True)
    partial = upload_dir / f"{upload_id}.part"  # renamed once the whole file is in
    size = 0
    try:
        with open(partial, "xb") as out:  # "x": never overwrite an existing file
            while chunk:
                size += len(chunk)
                if size > max_bytes:
                    break  # stop reading: the rest of the file is never copied
                out.write(chunk)
                chunk = stream.read(CHUNK_BYTES)
        if size > max_bytes:
            partial.unlink()
            limit_mb = max_bytes // (1024 * 1024)
            return RejectedFile(index, "FILE_TOO_LARGE", f"File is larger than {limit_mb} MB.")
        _write_metadata(upload_dir, upload_id, name)  # first, so a stored PDF always has its metadata
        partial.replace(upload_dir / stored_name(upload_id))
    except BaseException:
        partial.unlink(missing_ok=True)
        (upload_dir / metadata_name(upload_id)).unlink(missing_ok=True)
        raise
    return AcceptedFile(index=index, upload_id=upload_id, file=name, size_bytes=size)


def delete_stored(upload_dir: Path, accepted: list[AcceptedFile]) -> None:
    """Remove stored files and their metadata again, e.g. when the job for them could not be created."""
    for item in accepted:
        (upload_dir / stored_name(item.upload_id)).unlink(missing_ok=True)
        (upload_dir / metadata_name(item.upload_id)).unlink(missing_ok=True)


def open_pdf(path: Path, max_pages: int):
    """Open a stored PDF with PyMuPDF (worker only). Raises PdfFileError with a clear message."""
    import pymupdf

    try:
        document = pymupdf.open(path, filetype="pdf")
    except Exception:
        raise PdfFileError("CORRUPT", "the file is damaged or not a valid PDF.") from None
    if document.needs_pass or document.is_encrypted:
        document.close()
        raise PdfFileError("ENCRYPTED", "the file is password-protected.")
    if document.page_count == 0:
        document.close()
        raise PdfFileError("CORRUPT", "the file is damaged or not a valid PDF.")
    if document.page_count > max_pages:
        pages = document.page_count
        document.close()
        raise PdfFileError("TOO_MANY_PAGES", f"the file has {pages} pages; at most {max_pages} are allowed (PDF_MAX_PAGES).")
    return document
