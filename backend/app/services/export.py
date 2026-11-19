"""CSV and JSON exports of jobs, candidates and the match table (LLD §4.6, HLD §8.10).

- **Same query as the search.** Jobs and candidates use the search service's filter builder and
  sort, without paging, so an export holds exactly the rows of the table on screen.
- **Stored matches only.** The match table reads `matches`; nothing is recalculated. Each
  candidate's top N is ranked in SQL with the same order as GET /candidates/{id}/matches.
- **Streamed.** Rows come from a server-side cursor in batches of EXPORT_BATCH_ROWS and are
  written out one by one, so memory use does not grow with the size of the export. The query
  runs before the response starts, so a database error is still an error response.
- **CSV:** UTF-8, RFC 4180 quoting (Python's csv module), lists joined with "; ", ISO dates.
  A text cell that starts with = + - @ (or a tab or carriage return) gets a leading ' so a
  spreadsheet shows it as text instead of running it as a formula. Numbers are never changed.
- **JSON:** one array, each item the API's own schema (numbers as numbers, lists as arrays).
- **Privacy.** Internal columns (stored file paths, resume text, file hashes, job IDs of the
  uploads) are never selected. Every export is sent with `Cache-Control: no-store`.
"""

import csv
import io
import json
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Select, func, select

from app.db.session import SessionLocal
from app.matching import ranking
from app.matching.explanation import display, display_breakdown
from app.models import Candidate, Job, Match
from app.schemas.candidate import CandidateExportParams
from app.schemas.job import JobExportParams
from app.schemas.match import MatchExportParams, MatchExportRow
from app.services import search

EXPORT_BATCH_ROWS = 500
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
MEDIA_TYPES = {"csv": "text/csv; charset=utf-8", "json": "application/json"}
LEVEL_NAMES = {"required": "required", "nice_to_have": "nice-to-have"}


# --- Cells, rows and files -----------------------------------------------------------------------


def csv_cell(value: Any) -> str:
    """One CSV cell. Text that a spreadsheet would run as a formula is prefixed with "'"."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        value = search.number(value)
    if isinstance(value, (int, float)):
        return repr(value) if isinstance(value, float) else str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    text = str(value)
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


def joined(values: Iterable[str]) -> str:
    return "; ".join(values)


def skills_cell(items: list[dict]) -> str:
    """[{skill: Python, level: required}, ...] -> "Python (required); Redis (nice-to-have)"."""
    return joined(f"{item['skill']} ({LEVEL_NAMES.get(item['level'], item['level'])})" for item in items)


def education_cell(entries) -> str:
    """"B.Tech, Pune University (2013 - 2017); ..." from the education entries."""
    parts = []
    for entry in entries:
        text = ", ".join(part for part in (entry.degree, entry.institution) if part)
        if entry.years:
            text = f"{text} ({entry.years})" if text else entry.years
        parts.append(text)
    return joined(parts)


def filename(entity: str, extension: str, now: datetime | None = None) -> str:
    """jobs_2026-11-10T10-15-00Z.csv (HLD §8.10): UTC, no characters that need quoting."""
    stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"{entity}_{stamp}.{extension}"


def _open_rows(statement: Select) -> Iterator:
    """Run the query now (errors become an error response), then yield its rows from a server-side cursor."""
    session = SessionLocal()
    try:
        result = session.execute(statement.execution_options(yield_per=EXPORT_BATCH_ROWS))
    except BaseException:
        session.close()
        raise

    def rows() -> Iterator:
        try:
            yield from result
        finally:  # also when the client disconnects mid-download
            result.close()
            session.close()

    return rows()


def _csv_lines(header: list[str], rows: Iterator, to_cells: Callable[[Any], list]) -> Iterator[bytes]:
    buffer = io.StringIO()
    writer = csv.writer(buffer)  # QUOTE_MINIMAL, "\r\n" line endings (RFC 4180)

    def line(cells: list) -> bytes:
        writer.writerow(cells)
        data = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate()
        return data.encode("utf-8")

    yield line(header)
    for row in rows:
        yield line([csv_cell(cell) for cell in to_cells(row)])


def _json_array(rows: Iterator, to_model: Callable[[Any], BaseModel]) -> Iterator[bytes]:
    yield b"["
    first = True
    for row in rows:
        item = json.dumps(to_model(row).model_dump(mode="json"), ensure_ascii=False)
        yield (item if first else "," + item).encode("utf-8")
        first = False
    yield b"]"


def _response(entity: str, export_format: str, body: Iterator[bytes]) -> StreamingResponse:
    return StreamingResponse(body, media_type=MEDIA_TYPES[export_format], headers={
        "Content-Disposition": f'attachment; filename="{filename(entity, export_format)}"',
        "Cache-Control": "no-store",
    })


# --- Jobs ------------------------------------------------------------------------------------------

JOB_COLUMNS = ["job_id", "title", "company", "location", "job_type", "is_remote", "salary_min", "salary_max",
               "salary_currency", "salary_period", "salary_text", "posted_date", "min_experience_years",
               "required_skills", "nice_to_have_skills", "apply_url", "source", "source_url", "description",
               "created_at", "updated_at"]


def _job_cells(row) -> list:
    return [row.job_id, row.title, row.company, row.location, row.job_type, row.is_remote, row.salary_min,
            row.salary_max, row.salary_currency, row.salary_period, row.salary_text, row.posted_date,
            row.min_experience_years, joined(row.required_skills or []), joined(row.nice_to_have_skills or []),
            row.apply_url, row.source, row.source_url, row.description, row.created_at, row.updated_at]


def export_jobs(params: JobExportParams) -> StreamingResponse:
    rows = _open_rows(search.jobs_statement(params, detail=True))
    body = (_csv_lines(JOB_COLUMNS, rows, _job_cells) if params.format == "csv"
            else _json_array(rows, search.job_detail))
    return _response("jobs", params.format, body)


# --- Candidates ------------------------------------------------------------------------------------

CANDIDATE_COLUMNS = ["candidate_id", "name", "email", "phone", "city", "current_title", "years_experience", "skills",
                     "education", "summary", "source_file", "parsed_with_ocr"]


def _candidate_cells(row) -> list:
    candidate = search.candidate_summary(row)
    return [candidate.candidate_id, candidate.name, candidate.email, candidate.phone, candidate.city,
            candidate.current_title, row.years_experience, joined(candidate.skills),
            education_cell(candidate.education), candidate.summary, candidate.source_file, candidate.parsed_with_ocr]


def export_candidates(params: CandidateExportParams) -> StreamingResponse:
    rows = _open_rows(search.candidates_statement(params))
    body = (_csv_lines(CANDIDATE_COLUMNS, rows, _candidate_cells) if params.format == "csv"
            else _json_array(rows, search.candidate_summary))
    return _response("candidates", params.format, body)


# --- The match table -------------------------------------------------------------------------------

MATCH_COLUMNS = ["candidate_id", "candidate_name", "rank", "job_id", "job_title", "company", "score",
                 "matched_skills", "missing_skills", "required_points", "nice_to_have_points", "experience_points",
                 "location_points", "text_similarity", "explanation", "computed_at"]


def matches_statement(params: MatchExportParams) -> Select:
    """Each selected candidate's top N stored matches, ranked exactly like GET /candidates/{id}/matches."""
    rank = func.row_number().over(partition_by=Match.candidate_id,
                                  order_by=ranking.jobs_for_candidate_order()).label("rank")
    chosen = select(Candidate.candidate_id).where(*search.candidate_conditions(params))
    ranked = (select(Match.candidate_id, Match.job_id, Match.score, Match.matched_skills, Match.missing_skills,
                     Match.score_breakdown, Match.text_similarity, Match.explanation, Match.computed_at, rank)
              .where(Match.candidate_id.in_(chosen))
              .subquery("ranked"))
    return (select(ranked, Candidate.name.label("candidate_name"), Job.title.label("job_title"), Job.company)
            .join(Candidate, Candidate.candidate_id == ranked.c.candidate_id)
            .join(Job, Job.job_id == ranked.c.job_id)
            .where(ranked.c.rank <= params.top)
            .order_by(*search.candidate_order(params), ranked.c.rank))


def match_row(row) -> MatchExportRow:
    return MatchExportRow(
        candidate_id=row.candidate_id, candidate_name=row.candidate_name, rank=row.rank, job_id=row.job_id,
        job_title=row.job_title, company=row.company, score=display(row.score), matched_skills=row.matched_skills,
        missing_skills=row.missing_skills, breakdown=display_breakdown(row.score_breakdown),
        text_similarity=display(row.text_similarity), explanation=row.explanation, computed_at=row.computed_at,
    )


def _match_cells(row) -> list:
    item = match_row(row)
    points = item.breakdown
    return [item.candidate_id, item.candidate_name, item.rank, item.job_id, item.job_title, item.company, item.score,
            skills_cell(row.matched_skills), skills_cell(row.missing_skills), points.required.points,
            points.nice_to_have.points, points.experience.points, points.location.points, item.text_similarity,
            item.explanation, item.computed_at]


def export_matches(params: MatchExportParams) -> StreamingResponse:
    rows = _open_rows(matches_statement(params))
    body = (_csv_lines(MATCH_COLUMNS, rows, _match_cells) if params.format == "csv"
            else _json_array(rows, match_row))
    return _response("matches", params.format, body)
