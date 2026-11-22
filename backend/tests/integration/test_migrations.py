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


INITIAL = "98acdef52211"  # the revision before jobs.industry


def test_the_industry_migration_classifies_existing_jobs_and_changes_nothing_else(engine):
    """Upgrading a database that already holds jobs fills jobs.industry from title, description and skills;
    every other column, updated_at included, keeps its value. Downgrade removes the column again."""
    run_alembic("downgrade", INITIAL)
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO skills (canonical_name, category) VALUES "
                                    "('BLS', 'healthcare'), ('Patient Care', 'healthcare'), ('Python', 'language')"))
            connection.execute(text(
                "INSERT INTO jobs (job_id, title, description, apply_url, source, dedup_key, updated_at) VALUES "
                "('00000000-0000-4000-8000-000000000001', 'Registered Nurse', 'Care for patients.', 'https://a.example/1', "
                " 'greenhouse', 'k1', '2026-01-01T00:00:00Z'), "
                "('00000000-0000-4000-8000-000000000002', 'Barista', NULL, 'https://a.example/2', 'generic', 'k2', "
                " '2026-01-01T00:00:00Z'), "
                "('00000000-0000-4000-8000-000000000003', 'Associate', NULL, 'https://a.example/3', 'mock_static', 'k3', "
                " '2026-01-01T00:00:00Z')"))
            connection.execute(text(
                "INSERT INTO job_skills (job_id, skill_id, requirement_level) "
                "SELECT '00000000-0000-4000-8000-000000000001', skill_id, 'required' FROM skills "
                "WHERE canonical_name IN ('BLS', 'Patient Care')"))
            before = connection.execute(text("SELECT * FROM jobs ORDER BY job_id")).mappings().all()

        run_alembic("upgrade", "head")
        with engine.connect() as connection:
            after = connection.execute(text("SELECT * FROM jobs ORDER BY job_id")).mappings().all()
        assert [row["industry"] for row in after] == ["healthcare", "other", "other"]
        assert [{k: v for k, v in row.items() if k != "industry"} for row in after] == [dict(row) for row in before]

        run_alembic("downgrade", INITIAL)
        with engine.connect() as connection:
            columns = {c["name"] for c in inspect(connection).get_columns("jobs")}
            assert "industry" not in columns
            assert connection.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 3  # the jobs are kept
    finally:
        run_alembic("upgrade", "head")
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE job_skills, jobs, skills RESTART IDENTITY CASCADE"))
