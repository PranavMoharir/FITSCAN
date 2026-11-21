"""/matching/weights: the default, active and current-results scoring weights (LLD §4.5, §7.4).

Read-only. The weights themselves are set per match run (POST /background-jobs/match).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.match import ActiveWeights, MatchWeightsInfo, ResultsWeights
from app.services import background_jobs as service

router = APIRouter(prefix="/matching", tags=["matching"])


@router.get(
    "/weights", response_model=MatchWeightsInfo,
    summary="Scoring weights: default, active and those of the current results",
    description="`default` is MATCH_WEIGHTS. `active` is what a match run started without weights uses: the weights "
                "of the most recently created queued, running or completed match run that recorded them, otherwise "
                "the default. `results` names the run whose results are stored; its weights are null when that run "
                "is from before weights were recorded.",
)
def get_weights(db: Session = Depends(get_db)) -> MatchWeightsInfo:
    weights, job_id = service.active_weights(db)
    results = service.results_weights(db)
    return MatchWeightsInfo(
        default=service.default_weights(),
        active=ActiveWeights(weights=weights, source="match_run" if job_id else "default", background_job_id=job_id),
        results=ResultsWeights(**results) if results else None,
    )
