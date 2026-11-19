"""Scanned-page detection and OCR with Tesseract (LLD §6.5, HLD §8.7).

A page counts as **scanned** when it has almost no extractable text (fewer than
`OCR_MIN_TEXT_CHARS` characters) but contains at least one image. Such a page is rendered to a
grayscale image with PyMuPDF at about 300 DPI and passed to Tesseract through pytesseract.

OCR is a Should requirement; flagging is the permitted fallback. Every failure becomes an
`OcrError` with a short reason ("Tesseract is not installed", "timed out after 60 s", "no text"),
and the caller flags the page. Reasons never contain page content.

Tesseract runs locally, so no resume data leaves the system. It is installed in the worker
image only.
"""

import functools
import logging

import pymupdf

logger = logging.getLogger(__name__)

OCR_DPI = 300
# Longest side of the rendered image. An A4 page at 300 DPI is 3508 px high. A larger page is
# rendered at a lower resolution, so a huge (or malicious) page size cannot exhaust memory.
MAX_RENDER_PIXELS = 5000
MIN_OCR_TEXT_CHARS = 10  # less than this after OCR counts as "no text"

logging.getLogger("PIL").setLevel(logging.INFO)  # Pillow's debug lines are noise


class OcrError(Exception):
    """OCR could not read a page. `reason` is short and safe to log."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def is_scanned(text_chars: int, image_count: int, min_text_chars: int) -> bool:
    """Almost no extractable text, but at least one image: the page is a scan or a photo."""
    return text_chars < min_text_chars and image_count > 0


@functools.cache
def tesseract_version() -> str | None:
    """The installed Tesseract version, or None if the binary is missing (checked once per process)."""
    import pytesseract

    try:
        return str(pytesseract.get_tesseract_version())
    except Exception:
        return None


def render_page(page: pymupdf.Page):
    """The page as a grayscale Pillow image, at 300 DPI unless the page is very large."""
    from PIL import Image

    longest_side_points = max(page.rect.width, page.rect.height, 1)
    zoom = min(OCR_DPI / 72, MAX_RENDER_PIXELS / longest_side_points)
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY, alpha=False)
    return Image.frombytes("L", (pixmap.width, pixmap.height), pixmap.samples)


def ocr_page(page: pymupdf.Page, *, language: str, timeout_seconds: float) -> str:
    """Text of one scanned page. Raises OcrError if Tesseract is missing, times out or finds no text."""
    import pytesseract

    if tesseract_version() is None:
        raise OcrError("Tesseract is not installed")
    image = render_page(page)
    try:
        text = pytesseract.image_to_string(image, lang=language, timeout=timeout_seconds)
    except pytesseract.TesseractNotFoundError:
        raise OcrError("Tesseract is not installed") from None
    except pytesseract.TesseractError:  # Tesseract ran and reported an error (e.g. unknown language)
        raise OcrError("Tesseract failed (check OCR_LANGUAGE)") from None
    except RuntimeError as exc:  # pytesseract raises RuntimeError("Tesseract process timeout")
        if "timeout" in str(exc).lower():
            raise OcrError(f"timed out after {timeout_seconds:g} s") from None
        raise OcrError("Tesseract failed") from None
    if len("".join(text.split())) < MIN_OCR_TEXT_CHARS:
        raise OcrError("no text")
    return text
