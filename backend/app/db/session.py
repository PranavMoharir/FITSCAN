"""Database engine and sessions (LLD §2.3, §3.8).

- `engine` is created once per process. Creating it does not connect yet.
- `SessionLocal` makes sessions; `get_db` gives each API request its own session and always closes it.
- `check_database` is the connectivity check used by `GET /health`.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)

# Fail fast instead of hanging when the database host does not answer.
CONNECT_TIMEOUT_SECONDS = 3
HEALTH_CHECK_TIMEOUT_SECONDS = 3

engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,  # replaces connections the database has closed (e.g. after a restart)
    connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    # Error messages and logs never show the SQL parameters: they can be resume text or contact details.
    hide_parameters=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, closed when the request ends."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """One short transaction: commit on success, roll back on error, always close (worker tasks)."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database() -> bool:
    """Return True if PostgreSQL answers `SELECT 1` within the timeout."""
    try:
        with engine.connect() as connection:
            # Applies to this transaction only, so it never affects other queries.
            connection.execute(text(f"SET LOCAL statement_timeout = '{HEALTH_CHECK_TIMEOUT_SECONDS}s'"))
            connection.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError) as exc:
        logger.warning("Database check failed: %s", exc.__class__.__name__)
        return False
