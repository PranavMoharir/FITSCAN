"""OCR of scanned pages (LLD §6.5, §9.7).

The real-Tesseract tests are skipped automatically when the binary is missing (it is installed
in the worker image; see README "Running the OCR tests in the worker container").
"""

from datetime import date

import pymupdf
import pytesseract
import pytest

from app.config import get_settings
from app.resumes import ocr
from app.resumes.pipeline import parse_resume
from tests import resume_pdfs

needs_tesseract = pytest.mark.skipif(ocr.tesseract_version() is None, reason="Tesseract is not installed here")


def a_page():
    document = pymupdf.open()
    return document, document.new_page(width=595, height=842)


@pytest.mark.parametrize(("chars", "images", "scanned"), [(0, 1, True), (24, 2, True), (25, 1, False), (0, 0, False)])
def test_scanned_means_almost_no_text_but_an_image(chars, images, scanned):
    assert ocr.is_scanned(chars, images, min_text_chars=25) is scanned


def test_pages_render_at_300_dpi():
    _, page = a_page()
    image = ocr.render_page(page)
    width, height = image.size
    assert abs(width - 2480) <= 2 and abs(height - 3508) <= 2 and image.mode == "L"  # A4 at 300 DPI, grayscale


def test_a_huge_page_is_rendered_at_a_lower_resolution():
    document = pymupdf.open()
    page = document.new_page(width=14400, height=14400)  # 200 x 200 inches
    assert max(ocr.render_page(page).size) <= ocr.MAX_RENDER_PIXELS


@pytest.fixture
def tesseract_present(monkeypatch):
    monkeypatch.setattr(ocr, "tesseract_version", lambda: "5.0")


def run_ocr_raising(monkeypatch, error):
    def image_to_string(*args, **kwargs):
        raise error
    monkeypatch.setattr(pytesseract, "image_to_string", image_to_string)
    _, page = a_page()
    with pytest.raises(ocr.OcrError) as excinfo:
        ocr.ocr_page(page, language="eng", timeout_seconds=5)
    return excinfo.value.reason


def test_missing_tesseract_is_reported(monkeypatch):
    monkeypatch.setattr(ocr, "tesseract_version", lambda: None)
    _, page = a_page()
    with pytest.raises(ocr.OcrError, match="Tesseract is not installed"):
        ocr.ocr_page(page, language="eng", timeout_seconds=5)


def test_tesseract_disappearing_is_reported(monkeypatch, tesseract_present):
    assert run_ocr_raising(monkeypatch, pytesseract.TesseractNotFoundError()) == "Tesseract is not installed"


def test_a_timeout_is_reported(monkeypatch, tesseract_present):
    assert run_ocr_raising(monkeypatch, RuntimeError("Tesseract process timeout")) == "timed out after 5 s"


def test_a_tesseract_error_is_reported(monkeypatch, tesseract_present):
    reason = run_ocr_raising(monkeypatch, pytesseract.TesseractError(1, "Failed loading language 'xyz'"))
    assert reason == "Tesseract failed (check OCR_LANGUAGE)"


def test_empty_ocr_output_is_no_text(monkeypatch, tesseract_present):
    monkeypatch.setattr(pytesseract, "image_to_string", lambda *a, **kw: "  \n ~ \n")
    _, page = a_page()
    with pytest.raises(ocr.OcrError, match="no text"):
        ocr.ocr_page(page, language="eng", timeout_seconds=5)


def test_language_and_timeout_are_passed_to_tesseract(monkeypatch, tesseract_present):
    seen = {}

    def image_to_string(image, lang, timeout):
        seen.update(lang=lang, timeout=timeout)
        return "Plenty of recognised text here"
    monkeypatch.setattr(pytesseract, "image_to_string", image_to_string)
    _, page = a_page()
    assert ocr.ocr_page(page, language="eng+deu", timeout_seconds=7) == "Plenty of recognised text here"
    assert seen == {"lang": "eng+deu", "timeout": 7}


# --- With the real Tesseract binary (worker image) ---------------------------------------------------

@needs_tesseract
def test_real_ocr_reads_a_scanned_resume():
    document = pymupdf.open(stream=resume_pdfs.scanned(), filetype="pdf")
    text = ocr.ocr_page(document[0], language="eng", timeout_seconds=60)
    assert "Asha Verma" in text and "asha.verma@example.com" in text and "Experience" in text


@needs_tesseract
def test_real_ocr_resume_becomes_a_candidate(tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(resume_pdfs.scanned())
    parsed = parse_resume(path, source_file="scan.pdf", sha256="0" * 64, stored_path="scan.pdf",
                          settings=get_settings(), today=date(2026, 11, 18))
    record = parsed.record
    assert record.parsed_with_ocr and parsed.ocr_pages == [1]
    assert (record.name, record.email, record.city) == ("Asha Verma", "asha.verma@example.com", "Pune")
    assert {"Python", "Go", "PostgreSQL", "Docker"} <= set(record.skills)
