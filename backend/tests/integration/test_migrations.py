"""The initial Alembic migration: fresh upgrade, downgrade and upgrade again, models = database."""

from sqlalchemy import inspect, text

from tests.integration.helpers import run_alembic

TABLES = {
    "background_jobs",
    "background_job_logs",
    "jobs",
    "candidates",
    "skills",
    "job_skills",
    "candidate_skills",
    "matches",
}


def _state(engine) -> tuple[set[str], bool, str | None]:
    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        trgm = connection.execute(text("SELECT count(*) FROM pg_extension WHERE extname = 'pg_trgm'")).scalar() == 1
        version = None
        if "alembic_version" in tables:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    return tables - {"alembic_version"}, trgm, version


def _head() -> str:
    return run_alembic("heads").stdout.split()[0]


def test_fresh_upgrade_creates_the_eight_tables(engine):
    tables, trgm, version = _state(engine)
    assert tables == TABLES
    assert trgm, "pg_trgm extension must be installed by the migration"
    assert version == _head()


def test_single_migration_head():
    assert len(run_alembic("heads").stdout.strip().splitlines()) == 1


def test_models_and_database_have_no_differences(engine):
    # `alembic check` compares the models with the migrated database and fails on any difference.
    result = run_alembic("check")
    assert "No new upgrade operations detected" in result.stdout + result.stderr


def test_downgrade_then_upgrade_again(engine):
    run_alembic("downgrade", "base")
    tables, trgm, version = _state(engine)
    assert tables == set(), f"downgrade left tables behind: {tables}"
    assert not trgm, "downgrade must remove the pg_trgm extension"
    assert version is None

    run_alembic("upgrade", "head")
    tables, trgm, version = _state(engine)
    assert tables == TABLES
    assert trgm
    assert version == _head()
