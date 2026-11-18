"""SQLAlchemy models, one class per table (LLD Part 3).

Every model is imported here, so `import app.models` registers all eight tables on
`Base.metadata`. Alembic's env.py relies on this.
"""

from app.models.background_job import BackgroundJob, BackgroundJobLog
from app.models.candidate import Candidate, CandidateSkill
from app.models.job import Job, JobSkill
from app.models.match import Match
from app.models.skill import Skill

__all__ = [
    "BackgroundJob",
    "BackgroundJobLog",
    "Candidate",
    "CandidateSkill",
    "Job",
    "JobSkill",
    "Match",
    "Skill",
]
