"""CSV cells, formula-injection protection, escaping, JSON streaming and filenames of the exports (HLD §8.10). Offline."""

import csv
import io
import json
import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.schemas.candidate import EducationEntry
from app.services import export


@pytest.mark.parametrize(
    ("value", "cell"),
    [
        ("=HYPERLINK(\"http://evil.example\",\"click\")", "'=HYPERLINK(\"http://evil.example\",\"click\")"),
        ("+cmd|' /C calc'!A0", "'+cmd|' /C calc'!A0"),
        ("-2+3", "'-2+3"),
        ("@SUM(A1:A9)", "'@SUM(A1:A9)"),
        ("\t=1+1", "'\t=1+1"),
        ("\r=1+1", "'\r=1+1"),
        ("Python (required); Redis (nice-to-have)", "Python (required); Redis (nice-to-have)"),
        ("a=b", "a=b"),                   # only a leading character is dangerous
        ("", ""),
        ("Bengaluru — ₹ 9,00,000", "Bengaluru — ₹ 9,00,000"),
    ],
)
def test_text_cells_are_made_safe(value, cell):
    assert export.csv_cell(value) == cell


@pytest.mark.parametrize(
    ("value", "cell"),
    [
        (None, ""), (True, "true"), (False, "false"), (3, "3"), (-5, "-5"),  # numbers are never prefixed
        (71.67, "71.67"), (Decimal("2.50"), "2.5"), (Decimal("900000"), "900000"), (0.0, "0.0"),
        (date(2026, 11, 3), "2026-11-03"),
        (datetime(2026, 11, 19, 12, 0, 5, tzinfo=UTC), "2026-11-19T12:00:05+00:00"),
        (uuid.UUID(int=1), "00000000-0000-0000-0000-000000000001"),
    ],
)
def test_other_cells(value, cell):
    assert export.csv_cell(value) == cell


def test_csv_quoting_round_trips():
    """Commas, quotes, line breaks and non-ASCII text survive a spreadsheet-compatible round trip."""
    tricky = ['Acme, "The Best" Inc.', "line one\nline two\r\nline three", "naïve café, 東京", "plain"]
    body = b"".join(export._csv_lines(["a", "b", "c", "d"], iter([tricky]), lambda row: row)).decode("utf-8")
    assert body.endswith("\r\n")
    assert list(csv.reader(io.StringIO(body, newline=""))) == [["a", "b", "c", "d"], tricky]


def test_empty_csv_is_the_header_only():
    body = b"".join(export._csv_lines(export.JOB_COLUMNS, iter([]), lambda row: row)).decode("utf-8")
    assert body == ",".join(export.JOB_COLUMNS) + "\r\n"


class Item(BaseModel):
    name: str
    value: Decimal | None
    when: date


def test_json_array_streaming():
    rows = [SimpleNamespace(name='quote " and \\', value=Decimal("1.5"), when=date(2026, 1, 2)),
            SimpleNamespace(name="Pune — ₹", value=None, when=date(2026, 1, 3))]
    to_model = lambda row: Item(name=row.name, value=row.value, when=row.when)  # noqa: E731
    chunks = list(export._json_array(iter(rows), to_model))
    data = json.loads(b"".join(chunks).decode("utf-8"))
    assert data == [{"name": 'quote " and \\', "value": "1.5", "when": "2026-01-02"},
                    {"name": "Pune — ₹", "value": None, "when": "2026-01-03"}]
    assert "₹".encode() in b"".join(chunks)  # UTF-8, not \\u escapes
    assert b"".join(export._json_array(iter([]), to_model)) == b"[]"


def test_skill_and_education_cells():
    assert export.skills_cell([{"skill": "Python", "level": "required"},
                               {"skill": "Redis", "level": "nice_to_have"}]) == "Python (required); Redis (nice-to-have)"
    assert export.skills_cell([]) == ""
    entries = [EducationEntry(degree="B.Tech", institution="Pune University", years="2013 - 2017"),
               EducationEntry(degree="M.Sc", institution=None, years=None),
               EducationEntry(degree=None, institution=None, years="2020")]
    assert export.education_cell(entries) == "B.Tech, Pune University (2013 - 2017); M.Sc; 2020"


def test_filenames():
    assert export.filename("jobs", "csv", datetime(2026, 11, 10, 10, 15, 0, tzinfo=UTC)) == "jobs_2026-11-10T10-15-00Z.csv"
    assert re.fullmatch(r"matches_\d{4}-\d\d-\d\dT\d\d-\d\d-\d\dZ\.json", export.filename("matches", "json"))


def test_media_types():
    assert export.MEDIA_TYPES == {"csv": "text/csv; charset=utf-8", "json": "application/json"}
