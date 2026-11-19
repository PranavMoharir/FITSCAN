"""/candidates (LLD §4.5). Search, detail and the required match route.

Responses carry the candidate fields of the approved contract (HLD §12.4, LLD §4.6) and never the
internal columns: the stored file path, the resume text, the file hash or the upload's job.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.candidate import CandidateDetail, CandidateList, CandidateSearchParams
from app.schemas.common import ErrorResponse
from app.schemas.match import MAX_MATCHES, CandidateMatches
from app.services import matches as match_service
from app.services import search

router = APIRouter(prefix="/candidates", tags=["candidates"])

_ERRORS = {404: {"model": ErrorResponse, "description": "Unknown candidate"},
           422: {"model": ErrorResponse, "description": "Invalid ID or query parameter"}}


@router.get(
    "", response_model=CandidateList,
    responses={422: {"model": ErrorResponse, "description": "Invalid query parameter"}},
    summary="Search candidates",
    description="Filters combine with AND. `q` searches the name and the current title; `skill` accepts aliases; "
                "`city` also matches other spellings of a known city. Sorted by `name` (A to Z) or "
                "`years_experience`; missing values last, equal values ordered by ID. Unknown query parameters "
                "are rejected with 422.",
)
def search_candidates(params: Annotated[CandidateSearchParams, Query()],
                      db: Session = Depends(get_db)) -> CandidateList:
    return search.search_candidates(db, params)


@router.get("/{candidate_id}", response_model=CandidateDetail, responses=_ERRORS, summary="One candidate",
            description="The candidate's fields and parse warnings. Its top jobs are at "
                        "GET /candidates/{candidate_id}/matches.")
def get_candidate(candidate_id: uuid.UUID, db: Session = Depends(get_db)) -> CandidateDetail:
    return search.get_candidate(db, candidate_id)


@router.get(
    "/{candidate_id}/matches", response_model=CandidateMatches, responses=_ERRORS,
    summary="Top jobs for a candidate",
    description="Stored results of the last match run, best first. Recompute them with POST /background-jobs/match.",
)
def candidate_matches(
    candidate_id: uuid.UUID,
    limit: int = Query(MAX_MATCHES, ge=1, le=MAX_MATCHES, description="How many jobs (default and maximum 10)"),
    db: Session = Depends(get_db),
) -> CandidateMatches:
    return match_service.top_jobs_for_candidate(db, candidate_id, limit)
