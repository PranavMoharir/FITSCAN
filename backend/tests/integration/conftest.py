"""Integration tests against a real PostgreSQL database.

They run only when TEST_DATABASE_URL is set; otherwise they are skipped, so a plain `pytest`
stays offline. With the database container published by docker-compose.dev.yml:

    docker compose exec db createdb -U app matching_test
    TEST_DATABASE_URL=postgresql+psycopg://app:change-me@127.0.0.1:5433/matching_test pytest tests/integration

The tests drop and recreate the whole schema, so the database name must end in "_test".
Each test runs inside a transaction that is rolled back afterwards.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from tests.integration.helpers import TEST_DATABASE_URL, run_alembic


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """A fresh database: empty schema, then `alembic upgrade head`."""
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set (see tests/integration/conftest.py)")
    if not (make_url(TEST_DATABASE_URL).database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must name a database ending in _test; the tests drop its schema")

    engine = create_engine(TEST_DATABASE_URL, connect_args={"connect_timeout": 3})
    with engine.begin() as connection:  # start from an empty database
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    run_alembic("upgrade", "head")
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """A session whose changes are rolled back after the test."""
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()


# --- Fixtures for tests that run the application's own code (API, services, worker task) ----------

TABLES = "background_job_logs, job_skills, candidate_skills, matches, jobs, candidates, skills, background_jobs"


@pytest.fixture
def app_db(engine: Engine, monkeypatch) -> Iterator[Engine]:
    """Point the application's session factory at the test database; empty the tables afterwards.

    Application code commits for real (as in production), so these tests clean up by TRUNCATE
    instead of a rolled-back transaction.
    """
    from app.config import get_settings
    from app.db import session as db_session

    db_session.SessionLocal.configure(bind=engine)
    monkeypatch.setattr(get_settings(), "job_heartbeat_timeout_seconds", 600)
    monkeypatch.setattr(get_settings(), "job_queued_timeout_seconds", 600)
    try:
        yield engine
    finally:
        db_session.SessionLocal.configure(bind=db_session.engine)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
def published(monkeypatch) -> list:
    """Replace Celery publishing with a stub that records calls (LLD §9.8)."""
    from app.services import background_jobs as service

    calls: list = []

    def publish(task_name, job_id):
        calls.append((task_name, job_id))
        return f"task-{len(calls)}"

    monkeypatch.setattr(service, "publish_task", publish)
    monkeypatch.setattr(service, "revoke_task", lambda task_id: calls.append(("revoke", task_id)))
    return calls


@pytest.fixture
def fast_crawler(monkeypatch):
    """Crawler settings for tests: no waiting between requests, one retry, the mock site allowed."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "crawler_default_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "crawler_max_retries", 1)
    monkeypatch.setattr(settings, "crawler_private_host_allowlist", ["mock-site"])
    monkeypatch.setattr(settings, "crawler_max_pages_limit", 500)
    monkeypatch.setattr("app.crawler.fetcher.time.sleep", lambda seconds: None)  # backoff waits
    return settings
