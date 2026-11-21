"""The match run: load all jobs and candidates, score every pair, replace all stored matches (LLD §7.3, §7.9).

    load jobs and candidates (canonical skills, experience, city, texts)
    fit TF-IDF on all job descriptions and resume texts               tfidf.py
    for each candidate (one progress item):
        for each job: exact score, breakdown, skill lists, explanation  scoring.py, explanation.py
    in ONE transaction: lock matches; stop if a newer run already saved; delete all rows,
                        insert the new ones (one computed_at); mark the run completed

Every pair is scored one at a time with the exact scoring function, and every pair is stored
(ADR-019): no vectorized scoring and no top-10-only storage. The task wrapper in
`worker/tasks.py` reports progress, handles cancellation and writes the heartbeat.

Two runs can be in progress at once (the worker runs several tasks). A run that started later
read newer data, so an older run must never replace its results (LLD §7.9):
`find_newer_completed_run` is called in the saving transaction, after taking the lock.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, insert, select, text, tuple_
from sqlalchemy.orm import Session

from app.matching import explanation
from app.matching.scoring import CandidateProfile, JobProfile, Weights, score_pair
from app.models import BackgroundJob, Candidate, CandidateSkill, Job, JobSkill, Match, Skill


@dataclass(frozen=True)
class JobInput:
    job_id: uuid.UUID
    profile: JobProfile
    text: str | None   # the description, for TF-IDF


@dataclass(frozen=True)
class CandidateInput:
    candidate_id: uuid.UUID
    profile: CandidateProfile
    text: str | None   # the resume text, for TF-IDF


@dataclass(frozen=True)
class MatchRow:
    candidate_id: uuid.UUID
    job_id: uuid.UUID
    score: float                       # full precision
    matched_skills: list[dict[str, str]]
    missing_skills: list[dict[str, str]]
    explanation: str
    score_breakdown: dict[str, Any]
    text_similarity: float

    def values(self, computed_at: datetime) -> dict[str, Any]:
        return {"candidate_id": self.candidate_id, "job_id": self.job_id, "score": self.score,
                "matched_skills": self.matched_skills, "missing_skills": self.missing_skills,
                "explanation": self.explanation, "score_breakdown": self.score_breakdown,
                "text_similarity": self.text_similarity, "computed_at": computed_at}


def load_inputs(session: Session) -> tuple[list[JobInput], list[CandidateInput]]:
    """All jobs and candidates with their canonical skills, ordered by ID."""
    job_skills: dict[uuid.UUID, dict[str, set[str]]] = defaultdict(lambda: {"required": set(), "nice_to_have": set()})
    for job_id, level, name in session.execute(
        select(JobSkill.job_id, JobSkill.requirement_level, Skill.canonical_name).join(Skill, Skill.skill_id == JobSkill.skill_id)
    ):
        job_skills[job_id][level].add(name)
    jobs = [
        JobInput(job_id=row.job_id, text=row.description, profile=JobProfile(
            required=frozenset(job_skills[row.job_id]["required"]),
            nice_to_have=frozenset(job_skills[row.job_id]["nice_to_have"]),
            min_experience_years=row.min_experience_years, location=row.location, is_remote=row.is_remote))
        for row in session.execute(select(Job.job_id, Job.description, Job.min_experience_years, Job.location,
                                          Job.is_remote).order_by(Job.job_id))
    ]

    candidate_skills: dict[uuid.UUID, set[str]] = defaultdict(set)
    for candidate_id, name in session.execute(
        select(CandidateSkill.candidate_id, Skill.canonical_name).join(Skill, Skill.skill_id == CandidateSkill.skill_id)
    ):
        candidate_skills[candidate_id].add(name)
    candidates = [
        CandidateInput(candidate_id=row.candidate_id, text=row.resume_text, profile=CandidateProfile(
            skills=frozenset(candidate_skills[row.candidate_id]), years_experience=row.years_experience, city=row.city))
        for row in session.execute(select(Candidate.candidate_id, Candidate.resume_text, Candidate.years_experience,
                                          Candidate.city).order_by(Candidate.candidate_id))
    ]
    return jobs, candidates


def score_candidate(candidate: CandidateInput, jobs: Sequence[JobInput], similarities: Sequence[float],
                    weights: Weights) -> list[MatchRow]:
    """One candidate against every job: one row per pair."""
    rows = []
    for job, similarity in zip(jobs, similarities, strict=True):
        result = score_pair(job.profile, candidate.profile, weights)
        score = float(result.score)  # the one conversion from the exact value
        matched, missing = explanation.skill_lists(result)
        parts = explanation.breakdown(result)
        rows.append(MatchRow(
            candidate_id=candidate.candidate_id, job_id=job.job_id, score=score, matched_skills=matched,
            missing_skills=missing, explanation=explanation.explain(score, parts, missing), score_breakdown=parts,
            text_similarity=similarity,
        ))
    return rows


def lock_matches(session: Session) -> None:
    """The EXCLUSIVE lock on `matches`: plain reads continue, saving runs take turns."""
    session.execute(text("LOCK TABLE matches IN EXCLUSIVE MODE"))


def find_newer_completed_run(session: Session, job_id: uuid.UUID, started_at: datetime) -> uuid.UUID | None:
    """Lock `matches`, then return a completed match run that started after this one, if any.

    "Newer" means a later `started_at` (set when the worker claimed the run, just before it loaded
    the data), with the run ID breaking an exact tie. A run is marked completed in the same
    transaction that saves its results, under this lock, so after the lock is taken every saved
    result is visible here (READ COMMITTED: each statement sees all committed rows).
    """
    lock_matches(session)
    return session.execute(
        select(BackgroundJob.background_job_id)
        .where(BackgroundJob.type == "match", BackgroundJob.status == "completed",
               tuple_(BackgroundJob.started_at, BackgroundJob.background_job_id) > tuple_(started_at, job_id))
        .order_by(BackgroundJob.started_at.desc(), BackgroundJob.background_job_id.desc())
        .limit(1)
    ).scalar_one_or_none()


def save_matches(session: Session, rows: Sequence[MatchRow]) -> datetime:
    """Replace ALL stored matches with `rows` in the caller's transaction; returns computed_at.

    Readers see either the complete old result or the complete new one (LLD §7.9). The EXCLUSIVE
    lock lets plain reads continue, but makes two match runs that finish together save one after
    the other, so the second deletes the first one's rows instead of colliding with them.
    """
    lock_matches(session)  # already held when the caller checked for a newer run first; taking it again is a no-op
    computed_at = session.execute(select(func.now())).scalar_one()  # the transaction's time: one value for all rows
    session.execute(delete(Match))
    if rows:
        session.execute(insert(Match), [row.values(computed_at) for row in rows])
    return computed_at
