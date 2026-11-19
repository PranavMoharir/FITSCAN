"""/candidates (LLD §4.5). So far only the required match route; search and detail come with the search phase."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import ErrorResponse
from app.schemas.match import MAX_MATCHES, CandidateMatches
from app.services import matches as service

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.get(
    "/{candidate_id}/matches", response_model=CandidateMatches,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Top jobs for a candidate",
    description="Stored results of the last match run, best first. Recompute them with POST /background-jobs/match.",
)
def candidate_matches(
    candidate_id: uuid.UUID,
    limit: int = Query(MAX_MATCHES, ge=1, le=MAX_MATCHES, description="How many jobs (default and maximum 10)"),
    db: Session = Depends(get_db),
) -> CandidateMatches:
    return service.top_jobs_for_candidate(db, candidate_id, limit)
