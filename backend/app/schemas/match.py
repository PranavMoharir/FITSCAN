"""Response models for GET /candidates/{id}/matches and GET /jobs/{id}/matches (LLD §4.6, §7.11; HLD §12.5).

`score` and every `points` value are 2-decimal display values. The order of `items` and each
`rank` come from the full-precision stored score and the tie-breakers (LLD §7.10).
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.matching import scoring
from app.schemas.candidate import CandidateFilterParams
from app.schemas.common import ExportFormat

SkillLevel = Literal["required", "nice_to_have"]
SkillRule = Literal[scoring.RATIO, scoring.NONE_LISTED, scoring.NO_REQUIRED_IDENTIFIED, scoring.NO_SKILLS_IDENTIFIED]
ExperienceRule = Literal[scoring.RATIO, scoring.NO_MINIMUM, scoring.YEARS_UNKNOWN]
LocationRule = Literal[scoring.REMOTE, scoring.SAME_CITY, scoring.DIFFERENT_CITY, scoring.CANDIDATE_CITY_UNKNOWN,
                       scoring.JOB_CITY_UNKNOWN]

MAX_MATCHES = 10  # default and maximum `limit` (HLD §12.5)


class SkillRef(BaseModel):
    skill: str
    level: SkillLevel


class SkillComponent(BaseModel):
    matched: int
    total: int
    ratio: float
    points: float
    rule: SkillRule = Field(description="ratio: matched ÷ total; none_listed: the job lists no nice-to-have skills "
                                        "(full points); no_required_identified / no_skills_identified: 0 points")


class ExperienceComponent(BaseModel):
    candidate_years: float | None
    minimum: float | None
    fit: float
    points: float
    rule: ExperienceRule


class LocationComponent(BaseModel):
    candidate_city: str | None
    job_location: str | None
    job_city: str | None = Field(description="The city found in job_location, as it was compared")
    fit: float
    points: float
    rule: LocationRule


class Breakdown(BaseModel):
    required: SkillComponent
    nice_to_have: SkillComponent
    experience: ExperienceComponent
    location: LocationComponent


Rank = Annotated[int, Field(ge=1, le=MAX_MATCHES)]
DisplayScore = Annotated[float, Field(ge=0, le=100, description="2-decimal display value of the stored full-precision score")]
Similarity = Annotated[float | None, Field(description="TF-IDF cosine similarity (2 decimals); only orders equal scores")]


class JobMatch(BaseModel):
    """One of a candidate's top jobs (fields in the order of HLD §12.5)."""

    rank: Rank
    job_id: uuid.UUID
    title: str
    company: str | None
    score: DisplayScore
    matched_skills: list[SkillRef]
    missing_skills: list[SkillRef]
    breakdown: Breakdown
    text_similarity: Similarity
    explanation: str


class CandidateMatch(BaseModel):
    """One of a job's top candidates: the same fields, with candidate details instead of job details."""

    rank: Rank
    candidate_id: uuid.UUID
    name: str | None
    current_title: str | None
    city: str | None
    score: DisplayScore
    matched_skills: list[SkillRef]
    missing_skills: list[SkillRef]
    breakdown: Breakdown
    text_similarity: Similarity
    explanation: str


class CandidateMatches(BaseModel):
    """GET /candidates/{id}/matches. `computed_at` is null when no match run has included this candidate."""

    candidate_id: uuid.UUID
    computed_at: datetime | None
    items: list[JobMatch]


class JobMatches(BaseModel):
    """GET /jobs/{id}/matches. `computed_at` is null when no match run has included this job."""

    job_id: uuid.UUID
    computed_at: datetime | None
    items: list[CandidateMatch]


# --- GET /exports/matches: the match table, top N jobs per candidate (LLD §4.6, decision LLD-10) ------


class MatchExportParams(CandidateFilterParams):
    """The /candidates filters choose the candidates; `top` is how many of each one's jobs (ranked as in
    GET /candidates/{id}/matches)."""

    format: ExportFormat
    top: int = Field(MAX_MATCHES, ge=1, le=MAX_MATCHES, description="Jobs per candidate (default and maximum 10)")


class MatchExportRow(BaseModel):
    """One row of the match table: (candidate, rank, job, score, skills, breakdown, explanation)."""

    candidate_id: uuid.UUID
    candidate_name: str | None
    rank: Rank
    job_id: uuid.UUID
    job_title: str
    company: str | None
    score: DisplayScore
    matched_skills: list[SkillRef]
    missing_skills: list[SkillRef]
    breakdown: Breakdown
    text_similarity: Similarity
    explanation: str
    computed_at: datetime


# --- GET /matching/weights (LLD §4.5, §7.4) -----------------------------------------------------------


class WeightValues(BaseModel):
    """Weights of the required, nice-to-have, experience and location components; they add up to 100."""

    required: int | float
    nice: int | float
    experience: int | float
    location: int | float


class ActiveWeights(BaseModel):
    weights: WeightValues
    source: Literal["match_run", "default"] = Field(
        description="match_run: the most recently created queued, running or completed run with recorded weights; "
                    "default: no such run, so MATCH_WEIGHTS")
    background_job_id: uuid.UUID | None = Field(description="The run the weights come from (source match_run)")


class ResultsWeights(BaseModel):
    background_job_id: uuid.UUID = Field(description="The run whose results are stored: the completed run that started last")
    weights: WeightValues | None = Field(description="null when the run is from before weights were recorded")


class MatchWeightsInfo(BaseModel):
    default: WeightValues = Field(description="MATCH_WEIGHTS: 70, 15, 10, 5 unless configured otherwise")
    active: ActiveWeights = Field(description="Used by a match run that is started without weights")
    results: ResultsWeights | None = Field(description="null when no match run has completed yet")
