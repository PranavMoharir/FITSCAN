"""Upload checks (API) and PDF opening checks (worker) (LLD §6.2, §6.3, §9.3, §9.7)."""

import io
import json
import uuid

import pymupdf
import pytest

from app.resumes.validation import (
    AcceptedFile,
    PdfFileError,
    RejectedFile,
    delete_stored,
    display_name,
    open_pdf,
    read_source_file,
    save_upload,
    stored_name,
)
from tests import resume_pdfs

MB = 1024 * 1024


class CountingStream(io.RawIOBase):
    """A very large upload that is produced on demand; counts how many bytes were actually read."""

    def __init__(self, size: int, head: bytes = b"%PDF-1.7\n"):
        self.size, self.head, self.position, self.bytes_read = size, head, 0, 0

    def read(self, n: int = -1) -> bytes:
        n = self.size - self.position if n < 0 else min(n, self.size - self.position)
        start = self.position
        self.position += n
        self.bytes_read += n
        data = bytearray(b"0" * n)
        overlap = self.head[start:start + n]
        data[: len(overlap)] = overlap
        return bytes(data)


def save(data: bytes, name: str = "cv.pdf", content_type: str | None = "application/pdf", folder=None, max_bytes=20 * MB):
    return save_upload(io.BytesIO(data), name, content_type, folder, max_bytes)


def names_in(folder) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def test_a_valid_pdf_is_stored_under_a_random_uuid_name(tmp_path):
    data = resume_pdfs.one_column()
    result = save(data, "Asha_Verma_CV.pdf", folder=tmp_path)
    assert isinstance(result, AcceptedFile)
    assert result.file == "Asha_Verma_CV.pdf" and result.size_bytes == len(data)
    uuid.UUID(result.upload_id)  # a real UUID
    # The PDF and its metadata file: UUID names only, the original name is not a path.
    assert names_in(tmp_path) == [f"{result.upload_id}.json", f"{result.upload_id}.pdf"]
    assert (tmp_path / f"{result.upload_id}.pdf").read_bytes() == data
    assert read_source_file(tmp_path, result.upload_id) == "Asha_Verma_CV.pdf"


def test_the_metadata_file_holds_only_the_original_name(tmp_path):
    result = save(resume_pdfs.one_column(), "Résumé – Asha.pdf", folder=tmp_path)
    raw = (tmp_path / f"{result.upload_id}.json").read_text(encoding="utf-8")
    assert json.loads(raw) == {"source_file": "Résumé – Asha.pdf"}
    assert raw.isascii()  # non-ASCII names are escaped


@pytest.mark.parametrize("content", [None, "not json", '{"other": 1}', '["a"]', '{"source_file": ""}'])
def test_missing_or_broken_metadata_gives_no_name(tmp_path, content):
    upload_id = str(uuid.uuid4())
    if content is not None:
        (tmp_path / f"{upload_id}.json").write_text(content, encoding="utf-8")
    assert read_source_file(tmp_path, upload_id) is None


@pytest.mark.parametrize(("raw", "shown"), [
    ("../../etc/passwd.pdf", "passwd.pdf"),
    ("C:\\Users\\someone\\Desktop\\cv.pdf", "cv.pdf"),
    ("cv\x00\n.pdf", "cv.pdf"),
    ("", "unnamed.pdf"),
    (None, "unnamed.pdf"),
])
def test_the_original_name_is_only_data(tmp_path, raw, shown):
    result = save(resume_pdfs.one_column(), raw, folder=tmp_path)
    assert result.file == shown and read_source_file(tmp_path, result.upload_id) == shown
    assert names_in(tmp_path) == [f"{result.upload_id}.json", f"{result.upload_id}.pdf"]  # nothing outside tmp_path


def test_results_carry_the_position_of_the_file_in_the_request(tmp_path):
    accepted = save_upload(io.BytesIO(resume_pdfs.one_column()), "a.pdf", "application/pdf", tmp_path, 20 * MB, index=3)
    rejected = save_upload(io.BytesIO(b"text"), "b.txt", "text/plain", tmp_path, 20 * MB, index=4)
    assert (accepted.index, rejected.index) == (3, 4)


def test_long_names_are_shortened():
    assert len(display_name("x" * 400 + ".pdf")) == 255


@pytest.mark.parametrize(("data", "name", "content_type"), [
    (b"Hello, these are my notes.", "notes.txt", "text/plain"),     # not a PDF at all
    (b"Hello, these are my notes.", "notes.pdf", "application/pdf"),  # extension and type lie: signature decides
    (resume_pdfs.one_column(), "cv.txt", "application/pdf"),          # declared as something else
    (resume_pdfs.one_column(), "cv.pdf", "text/plain"),
    (resume_pdfs.one_column(), "cv.docx", None),
    (b"", "empty.pdf", "application/pdf"),
    (b" %PDF-1.7\n", "late.pdf", "application/pdf"),                 # the signature must come first
])
def test_files_that_are_not_pdfs_are_rejected(tmp_path, data, name, content_type):
    result = save(data, name, content_type, folder=tmp_path)
    assert result == RejectedFile(0, "NOT_A_PDF", "File is not a PDF document.")  # the name is never echoed
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("content_type", ["application/octet-stream", None, "application/pdf; charset=binary"])
def test_generic_content_types_are_allowed_because_the_signature_decides(tmp_path, content_type):
    assert isinstance(save(resume_pdfs.one_column(), "cv.pdf", content_type, folder=tmp_path), AcceptedFile)


def test_a_file_without_extension_but_with_the_signature_is_accepted(tmp_path):
    assert isinstance(save(resume_pdfs.one_column(), "resume", None, folder=tmp_path), AcceptedFile)


def test_an_oversized_file_is_rejected_while_streaming(tmp_path):
    stream = CountingStream(size=500 * MB)  # never exists in memory or on disk
    result = save_upload(stream, "cv_09.pdf", "application/pdf", tmp_path, 20 * MB)
    assert result == RejectedFile(0, "FILE_TOO_LARGE", "File is larger than 20 MB.")
    assert stream.bytes_read <= 20 * MB + 64 * 1024  # reading stopped right after the limit
    assert list(tmp_path.iterdir()) == []            # the partial copy was removed


def test_a_file_of_exactly_the_limit_is_accepted(tmp_path):
    result = save_upload(CountingStream(size=2 * MB), "cv.pdf", "application/pdf", tmp_path, 2 * MB)
    assert isinstance(result, AcceptedFile) and result.size_bytes == 2 * MB


def test_one_byte_over_the_limit_is_rejected(tmp_path):
    result = save_upload(CountingStream(size=2 * MB + 1), "cv.pdf", "application/pdf", tmp_path, 2 * MB)
    assert result.code == "FILE_TOO_LARGE" and "2 MB" in result.message


def test_stored_files_and_their_metadata_can_be_removed_again(tmp_path):
    accepted = [save(resume_pdfs.one_column(), folder=tmp_path) for _ in range(2)]
    assert len(names_in(tmp_path)) == 4
    delete_stored(tmp_path, accepted)
    assert list(tmp_path.iterdir()) == []


def test_stored_names_are_always_uuid_names():
    upload_id = str(uuid.uuid4())
    assert stored_name(upload_id) == f"{upload_id}.pdf"
    with pytest.raises(ValueError):
        stored_name("../../etc/passwd")


# --- Opening in the worker -----------------------------------------------------------------------


def write(tmp_path, data: bytes):
    path = tmp_path / f"{uuid.uuid4()}.pdf"
    path.write_bytes(data)
    return path


def test_a_valid_pdf_opens(tmp_path):
    with open_pdf(write(tmp_path, resume_pdfs.one_column()), max_pages=20) as document:
        assert document.page_count == 1


@pytest.mark.parametrize(("data", "code", "message"), [
    (resume_pdfs.corrupt(), "CORRUPT", "the file is damaged or not a valid PDF."),
    (b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n", "CORRUPT", "the file is damaged or not a valid PDF."),  # no pages
    (resume_pdfs.encrypted(), "ENCRYPTED", "the file is password-protected."),
])
def test_corrupt_and_encrypted_files_fail_with_clear_messages(tmp_path, data, code, message):
    with pytest.raises(PdfFileError) as excinfo:
        open_pdf(write(tmp_path, data), max_pages=20)
    assert (excinfo.value.code, excinfo.value.message) == (code, message)


def test_a_pdf_with_too_many_pages_fails(tmp_path):
    with pytest.raises(PdfFileError) as excinfo:
        open_pdf(write(tmp_path, resume_pdfs.pages(4)), max_pages=3)
    assert excinfo.value.code == "TOO_MANY_PAGES"
    assert excinfo.value.message == "the file has 4 pages; at most 3 are allowed (PDF_MAX_PAGES)."


def test_a_pdf_with_only_an_owner_password_is_readable(tmp_path):
    """"Restrict editing" PDFs open without a password, so they are not refused as encrypted."""
    source = pymupdf.open(stream=resume_pdfs.one_column(), filetype="pdf")
    data = source.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner-secret", user_pw="", permissions=0)
    with open_pdf(write(tmp_path, data), max_pages=20) as document:
        assert "Asha Verma" in document[0].get_text()
