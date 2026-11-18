"""/background-jobs: create, list, read, cancel, logs (LLD §4.5, HLD §12.3).

Only the crawl type can be created so far; resume upload and match runs come in later phases.
Routers stay thin: validate the input, call the service, return a schema.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.background_job import (
    BackgroundJobCreated,
    BackgroundJobDetail,
    BackgroundJobList,
    BackgroundJobStatus,
    BackgroundJobSummary,
    BackgroundJobType,
    CancelResult,
    CrawlRequest,
    LogLevel,
    LogLine,
    LogList,
)
from app.schemas.common import ErrorResponse
from app.services import background_jobs as service

router = APIRouter(prefix="/background-jobs", tags=["background jobs"])

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
_ERRORS = {404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}}


@router.post(
    "/crawl", status_code=202, response_model=BackgroundJobCreated,
    responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse, "description": "Broker unavailable"}},
    summary="Start a crawl",
)
def create_crawl(request: CrawlRequest, db: Session = Depends(get_db)) -> BackgroundJobCreated:
    return BackgroundJobCreated.of(service.create_crawl_job(db, request))


@router.get("", response_model=BackgroundJobList, responses={422: {"model": ErrorResponse}}, summary="List background jobs")
def list_background_jobs(
    type: BackgroundJobType | None = None,
    status: BackgroundJobStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
) -> BackgroundJobList:
    items, total = service.list_jobs(db, job_type=type, status=status, page=page, page_size=page_size)
    return BackgroundJobList(items=[BackgroundJobSummary.of(j) for j in items], total=total, page=page, page_size=page_size)


@router.get("/{background_job_id}", response_model=BackgroundJobDetail, responses=_ERRORS, summary="One background job")
def get_background_job(background_job_id: uuid.UUID, db: Session = Depends(get_db)) -> BackgroundJobDetail:
    return BackgroundJobDetail.of(service.get_job(db, background_job_id))


@router.post(
    "/{background_job_id}/cancel", response_model=CancelResult, response_model_exclude_none=True,
    responses={**_ERRORS, 202: {"model": CancelResult, "description": "Running job asked to stop"},
               409: {"model": ErrorResponse, "description": "Already finished"}},
    summary="Cancel a background job",
)
def cancel_background_job(background_job_id: uuid.UUID, db: Session = Depends(get_db)):
    status_code, body = service.cancel_job(db, background_job_id)
    return JSONResponse(status_code=status_code, content=CancelResult(**body).model_dump(exclude_none=True))


@router.get(
    "/{background_job_id}/logs", response_model=LogList, response_model_exclude_none=True, responses=_ERRORS,
    summary="Log lines, oldest first",
)
def get_background_job_logs(
    background_job_id: uuid.UUID,
    after_id: int = Query(0, ge=0, description="Only lines with a larger log_id"),
    level: LogLevel | None = Query(None, description="Minimum level: INFO also returns WARNING and ERROR"),
    db: Session = Depends(get_db),
) -> LogList:
    items, next_after_id = service.get_logs(db, background_job_id, after_id=after_id, min_level=level)
    return LogList(items=[LogLine.model_validate(i, from_attributes=True) for i in items], next_after_id=next_after_id)
