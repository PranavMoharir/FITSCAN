"""Text extraction: reading order, two columns, tables, garbled text, scanned pages (LLD §6.4-6.5, §9.7)."""

import pymupdf
import pytest

from app.resumes import ocr, text_extraction
from app.resumes.text_extraction import Block, Line, OcrSettings, clean_text, extract_text, looks_garbled, order_blocks
from tests import resume_pdfs


def extract(tmp_path, data: bytes, settings: OcrSettings | None = None, **kwargs):
    path = tmp_path / "file.pdf"
    path.write_bytes(data)
    with pymupdf.open(path) as document:
        return extract_text(document, path, settings or OcrSettings(), **kwargs)


def block(x0, y0, x1, y1, text):
    return Block(x0, y0, x1, y1, [Line(text, 1, top=y0)])


# --- Reading order with plain blocks ----------------------------------------------------------------

def test_one_column_blocks_are_read_top_to_bottom_then_left_to_right():
    blocks = [block(50, 200, 400, 215, "third"), block(50, 100, 300, 115, "first"),
              block(400, 101, 545, 115, "second, same row")]
    ordered, two_columns = order_blocks(blocks, 595)
    assert [b.lines[0].text for b in ordered] == ["first", "second, same row", "third"]
    assert not two_columns


def test_two_columns_are_read_left_column_first_after_the_full_width_header():
    header = block(40, 40, 555, 70, "Name across the page")
    left = [block(40, 120 + 40 * i, 200, 150 + 40 * i, f"left {i} " + "word " * 12) for i in range(5)]
    right = [block(235, 120 + 40 * i, 555, 150 + 40 * i, f"right {i} " + "word " * 20) for i in range(5)]
    ordered, two_columns = order_blocks(right + [header] + left, 595)
    texts = [b.lines[0].text.split(" word")[0] for b in ordered]
    assert two_columns
    assert texts == ["Name across the page", *[f"left {i}" for i in range(5)], *[f"right {i}" for i in range(5)]]


def test_right_aligned_dates_do_not_make_a_second_column():
    """One-column resume: wide text lines, plus short date blocks at the right edge of the same rows."""
    blocks = []
    for i in range(6):
        blocks.append(block(50, 100 + 30 * i, 320, 115 + 30 * i, f"Role {i} at a company " + "x" * 30))
        blocks.append(block(470, 100 + 30 * i, 545, 115 + 30 * i, "2019-2021"))
    ordered, two_columns = order_blocks(blocks, 595)
    assert not two_columns
    assert [b.lines[0].text[:6] for b in ordered[:4]] == ["Role 0", "2019-2", "Role 1", "2019-2"]


def test_short_left_aligned_lines_are_not_two_columns():
    blocks = [block(50, 100 + 20 * i, 120 + 10 * i, 115 + 20 * i, f"Item {i}") for i in range(10)]
    assert order_blocks(blocks, 595)[1] is False


# --- Real PDFs ---------------------------------------------------------------------------------------

def test_one_column_resume_text_and_font_sizes(tmp_path):
    extracted = extract(tmp_path, resume_pdfs.one_column())
    lines = extracted.lines
    assert lines[0].text == "Asha Verma" and lines[0].size == pytest.approx(22) and lines[0].bold
    assert lines[1].text == "Senior Backend Engineer"
    assert "Jan 2021 – Present" in extracted.text           # Unicode dashes survive
    assert extracted.pages[0].source == "text" and not extracted.pages[0].two_columns
    assert extracted.ocr_pages == [] and extracted.events == []


def test_two_column_resume_keeps_the_left_column_before_the_right(tmp_path):
    extracted = extract(tmp_path, resume_pdfs.two_column(resume_pdfs.PEOPLE["rahul"]))
    text = extracted.text
    assert extracted.pages[0].two_columns
    order = [text.index(marker) for marker in
             ("Rahul Mehta", "Contact", "Skills", "Power BI", "Education", "Summary", "Experience", "Wrote SQL reports")]
    assert order == sorted(order)
    # Each column's lines stay whole: no line mixes text from the two columns.
    assert "Data analyst who turns product data into dashboards and forecasts for" in text.splitlines()


def test_skills_in_a_table_are_extracted_as_cells(tmp_path):
    extracted = extract(tmp_path, resume_pdfs.table())
    assert extracted.table_cells == ["Languages", "Python, C++, C#", "Frameworks", ".NET, Node.js, React",
                                     "Data", "R", "Cloud", "AWS, Docker"]
    assert "Python, C++, C#" in extracted.text  # cell text is part of the page text as well


def test_scanned_page_with_ocr_disabled_is_flagged(tmp_path):
    extracted = extract(tmp_path, resume_pdfs.scanned(), OcrSettings(enabled=False))
    assert extracted.pages[0].source == "scanned" and extracted.unread_scanned_pages == [1]
    assert [(e.level, e.message) for e in extracted.events] == [
        ("WARNING", "page 1 is scanned, but OCR is disabled (OCR_ENABLED=false).")]


def test_scanned_page_text_comes_from_ocr(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "ocr_page", lambda page, **kw: "Kiran Rao\nData Engineer\n\nSkills\nPython, Spark\n")
    extracted = extract(tmp_path, resume_pdfs.scanned(), OcrSettings(min_text_chars=25))
    assert extracted.ocr_pages == [1]
    assert [(l.text, l.block) for l in extracted.lines] == [
        ("Kiran Rao", 0), ("Data Engineer", 0), ("Skills", 1), ("Python, Spark", 1)]
    assert extracted.events[0].message == "page 1: OCR completed (41 characters)."


def test_failed_ocr_is_a_warning_with_the_reason(tmp_path, monkeypatch):
    def fail(page, **kw):
        raise ocr.OcrError("Tesseract is not installed")
    monkeypatch.setattr(ocr, "ocr_page", fail)
    extracted = extract(tmp_path, resume_pdfs.scanned())
    assert extracted.events[0].message == "page 1 is scanned and OCR produced no text (Tesseract is not installed)."
    assert extracted.text == ""


def test_a_page_with_text_is_never_sent_to_ocr(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "ocr_page", lambda *a, **kw: pytest.fail("OCR must not run"))
    assert extract(tmp_path, resume_pdfs.one_column()).pages[0].source == "text"


def test_garbled_text_falls_back_to_pdfplumber_words(tmp_path, monkeypatch):
    real = text_extraction.looks_garbled
    calls = []

    def first_call_garbled(text):
        calls.append(text)
        return len(calls) == 1 or real(text)  # PyMuPDF's text "looks garbled"; pdfplumber's does not
    monkeypatch.setattr(text_extraction, "looks_garbled", first_call_garbled)
    extracted = extract(tmp_path, resume_pdfs.one_column())
    assert extracted.pages[0].source == "words"
    assert extracted.events[0].message == "page 1: the text layer looked garbled; pdfplumber's words were used."
    assert extracted.lines[0].text == "Asha Verma" and extracted.lines[0].size == pytest.approx(22)


def test_one_unreadable_page_does_not_stop_the_others(tmp_path, monkeypatch):
    real = text_extraction.extract_page

    def first_page_breaks(page, plumber_page, number, settings, events):
        if number == 1:
            raise RuntimeError("damaged page")
        return real(page, plumber_page, number, settings, events)
    monkeypatch.setattr(text_extraction, "extract_page", first_page_breaks)
    extracted = extract(tmp_path, resume_pdfs.pages(2))
    assert [p.source for p in extracted.pages] == ["unreadable", "text"]
    assert extracted.events[0].message == "page 1 could not be read and was skipped."


def test_on_page_is_called_after_every_page(tmp_path):
    seen = []
    extract(tmp_path, resume_pdfs.pages(3), on_page=seen.append)
    assert seen == [1, 2, 3]


@pytest.mark.parametrize(("text", "garbled"), [
    ("Senior engineer with experience in Python, Go and PostgreSQL across many products.", False),
    ("SeniorengineerwithexperienceinPythonGoandPostgreSQLacrossmanyproductsandteams", True),
    ("��� text with many replacement characters ����", True),
    ("(cid:12)(cid:15)(cid:3) unmapped glyphs (cid:44)(cid:45)(cid:46)(cid:47) more", True),
    ("short", False),
])
def test_garbled_text_detection(text, garbled):
    assert looks_garbled(text) is garbled


def test_clean_text_removes_control_characters_and_ligatures():
    assert clean_text("ﬁnance\x00 team\x07  lead  ") == "finance team lead"
