"""parse_resume on synthetic PDFs: layouts, failures and warnings (LLD §6.1-6.7, §9.3, §9.7). No database."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.config import get_settings
from app.resumes import ocr
from app.resumes.pipeline import FileFailed, file_sha256, parse_resume
from tests import resume_pdfs
from tests.resume_pdfs import Job, Person

TODAY = date(2026, 11, 18)


def parse(tmp_path, data: bytes, name: str = "cv.pdf", **kwargs):
    path = tmp_path / "stored.pdf"
    path.write_bytes(data)
    return parse_resume(path, source_file=name, sha256=file_sha256(path), stored_path="stored.pdf",
                        settings=kwargs.pop("settings", get_settings()), today=TODAY, **kwargs)


def failure(tmp_path, data: bytes, **kwargs) -> FileFailed:
    with pytest.raises(FileFailed) as excinfo:
        parse(tmp_path, data, **kwargs)
    return excinfo.value


@pytest.fixture
def no_tesseract(monkeypatch):
    monkeypatch.setattr(ocr, "tesseract_version", lambda: None)


def test_one_column_resume(tmp_path):
    parsed = parse(tmp_path, resume_pdfs.one_column(), "Asha_Verma_CV.pdf")
    r = parsed.record
    assert (r.name, r.email, r.phone, r.city, r.current_title) == (
        "Asha Verma", "asha.verma@example.com", "+919876543210", "Pune", "Senior Backend Engineer")
    assert r.years_experience == Decimal("6")  # the explicit "6+ years of experience" wins
    assert r.source_file == "Asha_Verma_CV.pdf" and r.stored_path == "stored.pdf" and not r.parsed_with_ocr
    assert len(r.file_sha256) == 64 and r.parse_warnings == []
    assert {"Python", "Go", "FastAPI", "PostgreSQL", "Docker", "Kubernetes", "C++", "Node.js"} <= set(r.skills)
    assert "Jan 2021 – Present" in r.resume_text
    assert parsed.pages == 1 and parsed.ocr_pages == []


def test_two_column_resume(tmp_path):
    r = parse(tmp_path, resume_pdfs.two_column(resume_pdfs.PEOPLE["rahul"])).record
    assert (r.name, r.city, r.current_title) == ("Rahul Mehta", "Bengaluru", "Data Analyst")
    assert r.years_experience == Decimal("8.4")  # Jul 2018 - Nov 2026, the overlap in 2020 counted once
    assert set(r.skills) == {"SQL", "Python", "Pandas", "Excel", "Power BI", "R"}
    assert [e.institution for e in r.education] == ["University of Mumbai"]


def test_skills_in_a_table_resume(tmp_path):
    r = parse(tmp_path, resume_pdfs.table(resume_pdfs.PEOPLE["meera"])).record
    assert {"Python", "C++", "C#", ".NET", "Node.js", "React", "R", "AWS", "Docker"} <= set(r.skills)


def test_overlapping_employment_without_an_explicit_statement(tmp_path):
    person = replace(Person(), summary="Backend engineer who likes reliable systems.", jobs=[
        Job("Engineer", "A", "Jan 2018 – Dec 2020"), Job("Engineer", "B", "Jan 2020 – Dec 2022")])
    assert parse(tmp_path, resume_pdfs.one_column(person)).record.years_experience == Decimal("5.0")


def test_malformed_optional_fields_become_null_with_warnings(tmp_path):
    person = replace(Person(), email="asha.verma@example", phone="Phone: 12345", location="Pune")
    r = parse(tmp_path, resume_pdfs.one_column(person)).record
    assert (r.email, r.phone, r.name) == (None, None, "Asha Verma")
    assert r.parse_warnings == ["invalid email removed", "invalid phone removed"]


def test_missing_optional_fields(tmp_path):
    person = Person(title="", email="", phone="", location="", summary="", jobs=[], education=[],
                    skills="Python, Docker, PostgreSQL, Kubernetes")
    r = parse(tmp_path, resume_pdfs.one_column(person)).record
    assert (r.email, r.phone, r.city, r.current_title, r.years_experience, r.education) == (
        None, None, None, None, None, [])
    assert r.skills == ["Docker", "Kubernetes", "PostgreSQL", "Python"]


def test_no_name_uses_the_file_name_with_a_warning(tmp_path):
    r = parse(tmp_path, resume_pdfs.one_column(replace(Person(), name="")), "cv_07.pdf").record
    assert r.name == "cv 07"
    assert "name not found; the file name is used instead" in r.parse_warnings


@pytest.mark.parametrize(("data", "message"), [
    (resume_pdfs.encrypted(), "the file is password-protected."),
    (resume_pdfs.corrupt(), "the file is damaged or not a valid PDF."),
])
def test_encrypted_and_corrupt_files_fail(tmp_path, data, message):
    error = failure(tmp_path, data)
    assert (error.level, error.message) == ("ERROR", message)


def test_too_many_pages_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "pdf_max_pages", 2)
    assert failure(tmp_path, resume_pdfs.pages(3)).message.startswith("the file has 3 pages")


def test_a_scanned_resume_without_tesseract_is_flagged_not_saved(tmp_path, no_tesseract):
    error = failure(tmp_path, resume_pdfs.scanned())
    assert (error.level, error.message) == ("WARNING", "scanned resume: OCR produced no text, so no candidate was created.")
    assert [e.message for e in error.events] == ["page 1 is scanned and OCR produced no text (Tesseract is not installed)."]


def test_ocr_timeout_is_flagged(tmp_path, monkeypatch):
    def timeout(page, **kwargs):
        raise ocr.OcrError("timed out after 60 s")
    monkeypatch.setattr(ocr, "ocr_page", timeout)
    error = failure(tmp_path, resume_pdfs.scanned())
    assert error.level == "WARNING" and "timed out after 60 s" in error.events[0].message


def test_a_blank_scan_is_flagged(tmp_path, monkeypatch):
    def nothing(page, **kwargs):
        raise ocr.OcrError("no text")
    monkeypatch.setattr(ocr, "ocr_page", nothing)
    assert failure(tmp_path, resume_pdfs.blank_scan()).level == "WARNING"


def test_ocr_text_makes_a_candidate_with_parsed_with_ocr(tmp_path, monkeypatch):
    text = ("KIRAN RAO\nkiran.rao@example.com | +91 90000 11111 | Hyderabad\n\nSkills\nPython, Go, Kubernetes\n\n"
            "Experience\nPlatform Engineer, Initech (Mar 2022 - Present)\n")
    monkeypatch.setattr(ocr, "ocr_page", lambda page, **kwargs: text)
    parsed = parse(tmp_path, resume_pdfs.scanned())
    r = parsed.record
    assert r.parsed_with_ocr and parsed.ocr_pages == [1]
    assert (r.name, r.email, r.city, r.current_title) == ("Kiran Rao", "kiran.rao@example.com", "Hyderabad",
                                                          "Platform Engineer")
    assert r.skills == ["Go", "Kubernetes", "Python"]
    assert [e.message.split(" (")[0] for e in parsed.events] == ["page 1: OCR completed"]


def test_too_little_text_is_not_a_candidate(tmp_path):
    import pymupdf

    document = pymupdf.open()
    document.new_page().insert_text((50, 80), "Hello", fontsize=11)
    error = failure(tmp_path, document.tobytes())
    assert (error.level, error.message) == ("ERROR", "no usable text could be extracted, so no candidate was created.")


def test_the_heartbeat_callback_runs_for_every_page(tmp_path):
    pages = []
    parse(tmp_path, resume_pdfs.pages(3), on_page=pages.append)
    assert pages == [1, 2, 3]


def test_failure_messages_never_contain_resume_content(tmp_path, no_tesseract):
    for data in (resume_pdfs.encrypted(), resume_pdfs.corrupt(), resume_pdfs.scanned()):
        error = failure(tmp_path, data, name="Asha_Verma_CV.pdf")
        texts = [error.message, *[e.message for e in error.events]]
        assert not any(secret in text for text in texts for secret in ("Asha", "Verma", "asha.verma", "98765"))
