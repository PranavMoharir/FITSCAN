"""/jobs: job postings (LLD §4.5). Search, detail and the required match route.

Routers stay thin: FastAPI validates the query through the Pydantic model, the service runs the
query, the schema shapes the answer.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import ErrorResponse
from app.schemas.job import JobList, JobSearchParams, JobView
from app.schemas.match import MAX_MATCHES, JobMatches
from app.services import matches as match_service
from app.services import search

router = APIRouter(prefix="/jobs", tags=["jobs"])

_ERRORS = {404: {"model": ErrorResponse, "description": "Unknown job"},
           422: {"model": ErrorResponse, "description": "Invalid ID or query parameter"}}


@router.get(
    "", response_model=JobList, responses={422: {"model": ErrorResponse, "description": "Invalid query parameter"}},
    summary="Search jobs",
    description="Filters combine with AND. `q` searches the title and the company; `skill` accepts aliases and "
                "matches required or nice-to-have skills; `max_required_years` also returns jobs with no minimum; "
                "`listing` is real or demo; `industry` is an industry code; `source` is a source name from "
                "GET /sources. "
                "Sorted by `posted_date` (newest first, jobs without a date last) or `title`; equal values are "
                "ordered by ID. Unknown query parameters are rejected with 422.",
)
def search_jobs(params: Annotated[JobSearchParams, Query()], db: Session = Depends(get_db)) -> JobList:
    return search.search_jobs(db, params)


@router.get("/{job_id}", response_model=JobView, responses=_ERRORS, summary="One job",
            description="Every stored field of the job, with its required and nice-to-have skills, whether it is "
                        "a real or a demo listing, and the evidence for its industry. Its top candidates are at "
                        "GET /jobs/{job_id}/matches.")
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> JobView:
    return search.get_job(db, job_id)


@router.get(
    "/{job_id}/matches", response_model=JobMatches, responses=_ERRORS,
    summary="Top candidates for a job",
    description="Stored results of the last match run, best first. Recompute them with POST /background-jobs/match.",
)
def job_matches(
    job_id: uuid.UUID,
    limit: int = Query(MAX_MATCHES, ge=1, le=MAX_MATCHES, description="How many candidates (default and maximum 10)"),
    db: Session = Depends(get_db),
) -> JobMatches:
    return match_service.top_candidates_for_job(db, job_id, limit)
