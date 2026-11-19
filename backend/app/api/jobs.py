"""/jobs: job postings (LLD §4.5). So far only the required match route; search and detail come with the search phase."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import ErrorResponse
from app.schemas.match import MAX_MATCHES, JobMatches
from app.services import matches as service

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get(
    "/{job_id}/matches", response_model=JobMatches,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Top candidates for a job",
    description="Stored results of the last match run, best first. Recompute them with POST /background-jobs/match.",
)
def job_matches(
    job_id: uuid.UUID,
    limit: int = Query(MAX_MATCHES, ge=1, le=MAX_MATCHES, description="How many candidates (default and maximum 10)"),
    db: Session = Depends(get_db),
) -> JobMatches:
    return service.top_candidates_for_job(db, job_id, limit)
