"""Text in reading order, two-column layouts, tables, a garbled-text fallback and OCR (LLD §6.4-6.5).

For each page:

1. **Text blocks.** PyMuPDF returns text blocks with their bounding boxes and, for every span,
   the font size and whether it is bold (used later to find the name and headings).
2. **Scanned pages.** Almost no text but an image: the page is read with OCR (`ocr.py`).
3. **Garbled text.** If PyMuPDF's text looks garbled (very few word breaks for the number of
   characters, or many unreadable characters), pdfplumber's word extraction is used instead.
4. **Reading order.** If the blocks form two groups side by side, separated by an empty vertical
   strip (the gutter), the page is two-column: the left column is read top to bottom, then the
   right column. A header that spans both columns comes first. Otherwise blocks are read top to
   bottom, then left to right. Without this step, lines of the two columns would be mixed.
5. **Tables.** pdfplumber extracts tables. Their cells are kept separately, because a cell is a
   skill context for the skill extractor (a lone "Go" in a cell is a skill).

The result keeps page numbers, so log lines can say which page needed OCR.
"""

import logging
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
import pymupdf

from app.resumes import ocr

logger = logging.getLogger(__name__)

# pdfminer (inside pdfplumber) prints parsed page content at DEBUG level: keep it quiet.
logging.getLogger("pdfminer").setLevel(logging.WARNING)
# MuPDF's own console messages repeat what our per-file messages already say.
pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)

# Text only (images are never loaded), whitespace kept, ligatures such as "ﬁ" expanded to "fi".
TEXT_FLAGS = pymupdf.TEXTFLAGS_TEXT & ~pymupdf.TEXT_PRESERVE_LIGATURES

ROW_TOLERANCE = 3.0          # points: blocks whose tops differ less than this are on the same row
WIDE_BLOCK_SHARE = 0.6       # a block wider than 60 % of the page spans both columns (e.g. the header)
GUTTER_ZONE = (0.25, 0.75)   # the gutter of a two-column page lies between 25 % and 75 % of its width
MIN_GUTTER = 6.0             # points
MIN_COLUMN_TEXT_SHARE = 0.15  # each column holds at least 15 % of the page's characters
MIN_COLUMN_WIDTH_SHARE = 0.2  # and is at least 20 % of the page wide (right-aligned dates are not a column)
MIN_COLUMN_OVERLAP = 0.5     # the columns run side by side for at least half the shorter one
WORD_GAP = 15.0              # points: a wider gap between two pdfplumber words starts a new block
MAX_TEXT_CHARS = 200_000     # per resume; a real resume is far shorter

_BAD_CHARS = re.compile(r"[�\x00-\x08\x0b\x0c\x0e-\x1f-]|\(cid:\d+\)")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass
class Line:
    text: str
    page: int          # 1-based
    block: int = 0     # paragraph number on the page (OCR text: separated by blank lines)
    size: float = 0.0  # largest font size on the line; 0 for OCR text
    bold: bool = False
    top: float = 0.0   # distance from the top of the page, in points


@dataclass
class Block:
    x0: float
    y0: float
    x1: float
    y1: float
    lines: list[Line]

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def chars(self) -> int:
        return sum(len(line.text) for line in self.lines)


@dataclass
class PageEvent:
    """Something worth a log line, e.g. "page 2: OCR completed". Never contains page text."""

    level: str  # INFO or WARNING
    page: int
    message: str


@dataclass
class PageText:
    number: int
    height: float
    source: str  # "text", "words" (pdfplumber fallback), "ocr", "scanned" (not read), "empty", "unreadable"
    lines: list[Line] = field(default_factory=list)
    table_cells: list[str] = field(default_factory=list)
    two_columns: bool = False


@dataclass
class OcrSettings:
    enabled: bool = True
    language: str = "eng"
    min_text_chars: int = 25
    timeout_seconds: float = 60.0


@dataclass
class ExtractedText:
    pages: list[PageText]
    events: list[PageEvent] = field(default_factory=list)

    @property
    def lines(self) -> list[Line]:
        return [line for page in self.pages for line in page.lines]

    @property
    def text(self) -> str:
        """The final text: pages in order, lines in reading order (stored as `resume_text`)."""
        pages = ["\n".join(line.text for line in page.lines) for page in self.pages if page.lines]
        return "\n\n".join(pages)[:MAX_TEXT_CHARS]

    @property
    def table_cells(self) -> list[str]:
        return [cell for page in self.pages for cell in page.table_cells]

    @property
    def ocr_pages(self) -> list[int]:
        return [page.number for page in self.pages if page.source == "ocr"]

    @property
    def unread_scanned_pages(self) -> list[int]:
        return [page.number for page in self.pages if page.source == "scanned"]


def clean_text(text: str) -> str:
    """Unicode compatibility forms folded ("ﬁ" -> "fi"), control characters removed, spaces squashed.

    PostgreSQL text cannot hold NUL characters, so they must never reach the database.
    """
    text = _CONTROL_CHARS.sub(" ", unicodedata.normalize("NFKC", text))
    return re.sub(r"[ \t ]+", " ", text).strip()


def looks_garbled(text: str) -> bool:
    """Very few word breaks for the number of characters, or many unreadable characters."""
    compact = "".join(text.split())
    if len(compact) < 40:
        return False
    bad = sum(len(match.group()) for match in _BAD_CHARS.finditer(text))
    if bad / len(compact) > 0.05:
        return True
    return len(compact) / max(1, len(text.split())) > 25


# --- Reading order --------------------------------------------------------------------------------


def reading_order(blocks: list[Block]) -> list[Block]:
    """Top to bottom; blocks on the same row (tops within ROW_TOLERANCE) left to right."""
    rows: list[list[Block]] = []
    for block in sorted(blocks, key=lambda b: (b.y0, b.x0)):
        if rows and block.y0 - rows[-1][0].y0 <= ROW_TOLERANCE:
            rows[-1].append(block)
        else:
            rows.append([block])
    return [block for row in rows for block in sorted(row, key=lambda b: b.x0)]


def _side_by_side(left: list[Block], right: list[Block], total_chars: int, page_width: float) -> bool:
    if not left or not right or total_chars == 0:
        return False
    if min(sum(b.chars for b in left), sum(b.chars for b in right)) < MIN_COLUMN_TEXT_SHARE * total_chars:
        return False
    for group in (left, right):  # e.g. right-aligned dates in a one-column resume are not a column
        if max(b.x1 for b in group) - min(b.x0 for b in group) < MIN_COLUMN_WIDTH_SHARE * page_width:
            return False
    top = max(min(b.y0 for b in left), min(b.y0 for b in right))
    bottom = min(max(b.y1 for b in left), max(b.y1 for b in right))
    shorter = min(max(b.y1 for b in left) - min(b.y0 for b in left), max(b.y1 for b in right) - min(b.y0 for b in right))
    return shorter > 0 and (bottom - top) >= MIN_COLUMN_OVERLAP * shorter


def find_column_gap(blocks: list[Block], page_width: float) -> float | None:
    """The x position of a two-column gutter, or None for any other layout.

    The gutter is an empty vertical strip in the middle half of the page that no narrow block
    crosses, with enough text side by side on both sides of it.
    """
    narrow = [b for b in blocks if b.width <= WIDE_BLOCK_SHARE * page_width]
    total_chars = sum(b.chars for b in blocks)
    low, high = GUTTER_ZONE[0] * page_width, GUTTER_ZONE[1] * page_width
    covered = sorted((max(b.x0, low), min(b.x1, high)) for b in narrow if b.x1 > low and b.x0 < high)
    free, cursor = [], low
    for start, end in covered:
        if start > cursor:
            free.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < high:
        free.append((cursor, high))
    for start, end in sorted(free, key=lambda strip: strip[1] - strip[0], reverse=True):
        if end - start < MIN_GUTTER:
            break
        gap = (start + end) / 2
        left = [b for b in narrow if b.x1 <= gap]
        right = [b for b in narrow if b.x0 >= gap]
        if _side_by_side(left, right, total_chars, page_width):
            return gap
    return None


def order_blocks(blocks: list[Block], page_width: float) -> tuple[list[Block], bool]:
    """Blocks in reading order, and whether the page was read as two columns."""
    gap = find_column_gap(blocks, page_width)
    if gap is None:
        return reading_order(blocks), False
    left = [b for b in blocks if b.x1 <= gap]
    right = [b for b in blocks if b.x0 >= gap]
    spanning = [b for b in blocks if b.x0 < gap < b.x1]
    columns_top = min(b.y0 for b in left + right)
    header = [b for b in spanning if b.y0 < columns_top]
    footer = [b for b in spanning if b.y0 >= columns_top]
    by_top = lambda group: sorted(group, key=lambda b: (b.y0, b.x0))  # noqa: E731
    return reading_order(header) + by_top(left) + by_top(right) + reading_order(footer), True


# --- Reading one page ---------------------------------------------------------------------------


def _text_blocks(page: pymupdf.Page, number: int) -> list[Block]:
    """PyMuPDF's text blocks, each line with its text, largest font size and bold flag."""
    blocks = []
    for raw in page.get_text("dict", flags=TEXT_FLAGS)["blocks"]:
        if raw.get("type") != 0:
            continue
        lines = []
        for raw_line in raw["lines"]:
            spans = [span for span in raw_line["spans"] if span["text"].strip()]
            if not spans:
                continue
            parts, previous_end = [], None
            for span in spans:  # a wide gap between two spans (e.g. a tab stop) becomes a space
                if previous_end is not None and span["bbox"][0] - previous_end > 1.5:
                    parts.append(" ")
                parts.append(span["text"])
                previous_end = span["bbox"][2]
            text = clean_text("".join(parts))
            if not text:
                continue
            bold = all(span["flags"] & pymupdf.TEXT_FONT_BOLD or "bold" in span["font"].lower() for span in spans)
            lines.append(Line(text, number, size=max(span["size"] for span in spans), bold=bold,
                              top=raw_line["bbox"][1]))
        if lines:
            blocks.append(Block(*raw["bbox"], lines=lines))
    return blocks


def _word_blocks(plumber_page, number: int) -> list[Block]:
    """Fallback for garbled pages: pdfplumber's words, grouped into lines, one block per line."""
    words = plumber_page.extract_words(extra_attrs=["size", "fontname"])
    rows: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        row = rows[-1] if rows else None
        if row and abs(word["top"] - row[0]["top"]) <= ROW_TOLERANCE and word["x0"] - row[-1]["x1"] <= WORD_GAP:
            row.append(word)
        else:
            rows.append([word])
    blocks = []
    for row in rows:
        text = clean_text(" ".join(word["text"] for word in row))
        if text:
            line = Line(text, number, size=max(w["size"] for w in row),
                        bold=all("bold" in w["fontname"].lower() for w in row), top=row[0]["top"])
            blocks.append(Block(row[0]["x0"], row[0]["top"], row[-1]["x1"], max(w["bottom"] for w in row), [line]))
    return blocks


def _table_cells(plumber_page) -> list[str]:
    if plumber_page is None:
        return []
    cells = []
    for table in plumber_page.extract_tables():
        for row in table:
            cells.extend(clean_text(cell) for cell in row if cell and cell.strip())
    return cells


def _ocr_lines(text: str, number: int) -> list[Line]:
    lines, block = [], 0
    for raw in text.splitlines():
        cleaned = clean_text(raw)
        if cleaned:
            lines.append(Line(cleaned, number, block=block))
        else:
            block += 1  # a blank line ends a paragraph
    return lines


def _scanned_page(page: pymupdf.Page, number: int, settings: OcrSettings, events: list[PageEvent]) -> PageText:
    if not settings.enabled:
        events.append(PageEvent("WARNING", number, f"page {number} is scanned, but OCR is disabled (OCR_ENABLED=false)."))
        return PageText(number, page.rect.height, "scanned")
    try:
        text = ocr.ocr_page(page, language=settings.language, timeout_seconds=settings.timeout_seconds)
    except ocr.OcrError as exc:
        events.append(PageEvent("WARNING", number, f"page {number} is scanned and OCR produced no text ({exc.reason})."))
        return PageText(number, page.rect.height, "scanned")
    lines = _ocr_lines(text, number)
    events.append(PageEvent("INFO", number, f"page {number}: OCR completed ({sum(len(l.text) for l in lines)} characters)."))
    return PageText(number, page.rect.height, "ocr", lines)


def extract_page(page: pymupdf.Page, plumber_page, number: int, settings: OcrSettings,
                 events: list[PageEvent]) -> PageText:
    blocks = _text_blocks(page, number)
    if ocr.is_scanned(sum(b.chars for b in blocks), len(page.get_images()), settings.min_text_chars):
        return _scanned_page(page, number, settings, events)
    if not blocks:
        return PageText(number, page.rect.height, "empty")

    source = "text"
    if looks_garbled(" ".join(line.text for block in blocks for line in block.lines)):
        word_blocks = _word_blocks(plumber_page, number) if plumber_page is not None else []
        if word_blocks and not looks_garbled(" ".join(b.lines[0].text for b in word_blocks)):
            blocks, source = word_blocks, "words"
            events.append(PageEvent("INFO", number, f"page {number}: the text layer looked garbled; pdfplumber's words were used."))
        else:
            events.append(PageEvent("WARNING", number, f"page {number}: the text looks garbled and may be read incorrectly."))

    ordered, two_columns = order_blocks(blocks, page.rect.width)
    lines = []
    for index, block in enumerate(ordered):
        for line in block.lines:
            line.block = index
            lines.append(line)
    return PageText(number, page.rect.height, source, lines, _table_cells(plumber_page), two_columns)


def extract_text(document: pymupdf.Document, pdf_path: Path, settings: OcrSettings,
                 on_page: Callable[[int], None] | None = None) -> ExtractedText:
    """Read every page of an opened PDF. One unreadable page is skipped; the others are kept.

    `on_page(number)` is called after each page, so a long OCR run keeps the job's heartbeat fresh.
    """
    pages: list[PageText] = []
    events: list[PageEvent] = []
    try:
        plumber = pdfplumber.open(pdf_path)
    except Exception:
        plumber = None  # PyMuPDF opened (or repaired) the file, pdfplumber cannot: no tables
        events.append(PageEvent("INFO", 1, "tables could not be read from this file; text extraction continues."))
    try:
        for index, page in enumerate(document):
            number = index + 1
            plumber_page = plumber.pages[index] if plumber is not None and index < len(plumber.pages) else None
            try:
                pages.append(extract_page(page, plumber_page, number, settings, events))
            except Exception as exc:
                logger.warning("Page %d could not be read: %s", number, type(exc).__name__)
                events.append(PageEvent("WARNING", number, f"page {number} could not be read and was skipped."))
                pages.append(PageText(number, page.rect.height, "unreadable"))
            finally:
                if plumber_page is not None:
                    plumber_page.close()  # frees pdfplumber's cached characters for this page
            if on_page is not None:
                on_page(number)
    finally:
        if plumber is not None:
            plumber.close()
    return ExtractedText(pages, events)
