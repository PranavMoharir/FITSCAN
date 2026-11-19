"""/exports: CSV or JSON downloads of jobs, candidates and the match table (LLD §4.6, HLD §8.10, §12.6).

Each export takes the filters and sort of its list, so it holds exactly what the table shows.
"""

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.schemas.candidate import CandidateExportParams
from app.schemas.common import ErrorResponse
from app.schemas.job import JobExportParams
from app.schemas.match import MatchExportParams
from app.services import export

router = APIRouter(prefix="/exports", tags=["exports"])


def _file(description: str) -> dict:
    return {
        200: {"description": description + " Sent as an attachment named `<entity>_<UTC time>.<csv|json>`.",
              "content": {"text/csv": {"schema": {"type": "string"}},
                          "application/json": {"schema": {"type": "array", "items": {"type": "object"}}}}},
        422: {"model": ErrorResponse, "description": "Invalid query parameter"},
    }


@router.get("/jobs", response_class=StreamingResponse, summary="Export jobs",
            responses=_file("Every job that GET /jobs finds with the same filters, in the same order, without paging."))
def export_jobs(params: Annotated[JobExportParams, Query()]) -> StreamingResponse:
    return export.export_jobs(params)


@router.get("/candidates", response_class=StreamingResponse, summary="Export candidates",
            responses=_file("Every candidate that GET /candidates finds with the same filters, in the same order."))
def export_candidates(params: Annotated[CandidateExportParams, Query()]) -> StreamingResponse:
    return export.export_candidates(params)


@router.get(
    "/matches", response_class=StreamingResponse, summary="Export the match table",
    description="One row per (candidate, rank, job): score, matched and missing skills, the points of each "
                "component and the explanation, read from the stored matches. The /candidates filters choose the "
                "candidates (decision LLD-10); with no filters this is the full match table of `samples/`.",
    responses=_file("Each chosen candidate's top `top` jobs, candidates in the /candidates order, then by rank."),
)
def export_matches(params: Annotated[MatchExportParams, Query()]) -> StreamingResponse:
    return export.export_matches(params)
