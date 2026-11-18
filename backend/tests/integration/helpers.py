"""Helpers shared by the integration tests: the Alembic runner, an error catcher and row factories."""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Candidate, Job, Match

BACKEND_DIR = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the Alembic command line against the test database, exactly as the API container does."""
    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL or "", "REDIS_URL": "redis://127.0.0.1:6379/15"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}"
    return result


def integrity_error(session: Session, *objects: object, statement=None):
    """Flush the objects (or run the statement) and return the database error it must raise."""
    with pytest.raises(IntegrityError) as excinfo:
        with session.begin_nested():
            if statement is not None:
                session.execute(statement)
            session.add_all(objects)
            session.flush()
    return excinfo.value.orig  # the psycopg error, with .sqlstate and .diag


# Minimal valid rows: only the NOT NULL columns, with unique values where required.
def make_job(**values) -> Job:
    defaults = {
        "title": "Backend Developer",
        "apply_url": f"https://jobs.example.com/{uuid.uuid4()}",
        "source": "test",
        "dedup_key": uuid.uuid4().hex,
    }
    return Job(**{**defaults, **values})


def make_candidate(**values) -> Candidate:
    defaults = {"source_file": "cv.pdf", "parsed_with_ocr": False, "file_sha256": uuid.uuid4().hex}
    return Candidate(**{**defaults, **values})


def make_match(candidate: Candidate, job: Job, **values) -> Match:
    defaults = {
        "candidate": candidate,
        "job": job,
        "score": 50.0,
        "matched_skills": [],
        "missing_skills": [],
        "explanation": "Score 50.00/100.",
        "score_breakdown": {},
    }
    return Match(**{**defaults, **values})
