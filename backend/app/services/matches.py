"""Top matches for one candidate or one job, read from the stored rows (LLD §7.10).

Rows come back in the ranking order of `matching/ranking.py` (full-precision score first, then the
tie-breakers). Ranks are numbered in that order, and only then are the score and the breakdown
rounded for display, so rounding can never change a rank.
"""

import uuid
from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.matching import ranking
from app.matching.explanation import display, display_breakdown
from app.models import Candidate, Job, Match
from app.schemas.match import CandidateMatch, CandidateMatches, JobMatch, JobMatches


def _shown(match: Match, rank: int) -> dict:
    """The fields every match item shares, rounded for display."""
    return {
        "rank": rank,
        "score": display(match.score),
        "matched_skills": match.matched_skills,
        "missing_skills": match.missing_skills,
        "breakdown": display_breakdown(match.score_breakdown),
        "text_similarity": display(match.text_similarity),
        "explanation": match.explanation,
    }


def _computed_at(rows) -> datetime | None:
    return rows[0].Match.computed_at if rows else None


def top_jobs_for_candidate(session: Session, candidate_id: uuid.UUID, limit: int) -> CandidateMatches:
    """GET /candidates/{id}/matches: 404 for an unknown candidate; no items before the first match run."""
    if not session.execute(select(exists().where(Candidate.candidate_id == candidate_id))).scalar():
        raise AppError(404, "NOT_FOUND", "Candidate not found.")
    rows = session.execute(
        select(Match, Job.title, Job.company)
        .join(Job, Job.job_id == Match.job_id)
        .where(Match.candidate_id == candidate_id)
        .order_by(*ranking.jobs_for_candidate_order())
        .limit(limit)
    ).all()
    items = [JobMatch(job_id=row.Match.job_id, title=row.title, company=row.company, **_shown(row.Match, rank))
             for rank, row in enumerate(rows, start=1)]
    return CandidateMatches(candidate_id=candidate_id, computed_at=_computed_at(rows), items=items)


def top_candidates_for_job(session: Session, job_id: uuid.UUID, limit: int) -> JobMatches:
    """GET /jobs/{id}/matches: 404 for an unknown job; no items before the first match run."""
    if not session.execute(select(exists().where(Job.job_id == job_id))).scalar():
        raise AppError(404, "NOT_FOUND", "Job not found.")
    rows = session.execute(
        select(Match, Candidate.name, Candidate.current_title, Candidate.city)
        .join(Candidate, Candidate.candidate_id == Match.candidate_id)
        .where(Match.job_id == job_id)
        .order_by(*ranking.candidates_for_job_order())
        .limit(limit)
    ).all()
    items = [CandidateMatch(candidate_id=row.Match.candidate_id, name=row.name, current_title=row.current_title,
                            city=row.city, **_shown(row.Match, rank))
             for rank, row in enumerate(rows, start=1)]
    return JobMatches(job_id=job_id, computed_at=_computed_at(rows), items=items)
