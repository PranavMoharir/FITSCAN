"""The migrated schema in PostgreSQL: keys, types, defaults, constraints, cascades and score precision."""

from fractions import Fraction

import pytest
from sqlalchemy import delete, func, inspect, select, text, update

from app.models import (
    BackgroundJob,
    BackgroundJobLog,
    Candidate,
    CandidateSkill,
    Job,
    JobSkill,
    Match,
    Skill,
)
from tests.integration.helpers import integrity_error, make_candidate, make_job, make_match

UNIQUE_VIOLATION, CHECK_VIOLATION, NOT_NULL_VIOLATION, FK_VIOLATION = "23505", "23514", "23502", "23503"


def _skill(session, name: str) -> Skill:
    skill = Skill(canonical_name=name, category="language")
    session.add(skill)
    session.flush()
    return skill


def _count(session, model, **where) -> int:
    stmt = select(func.count()).select_from(model)
    for column, value in where.items():
        stmt = stmt.where(getattr(model, column) == value)
    return session.execute(stmt).scalar_one()


# --- Structure ---------------------------------------------------------------------------------


def test_primary_keys(engine):
    expected = {
        "background_jobs": ["background_job_id"],
        "background_job_logs": ["log_id"],
        "jobs": ["job_id"],
        "candidates": ["candidate_id"],
        "skills": ["skill_id"],
        "job_skills": ["job_id", "skill_id"],
        "candidate_skills": ["candidate_id", "skill_id"],
        "matches": ["candidate_id", "job_id"],
    }
    insp = inspect(engine)
    assert {t: insp.get_pk_constraint(t)["constrained_columns"] for t in expected} == expected


def test_foreign_keys(engine):
    insp = inspect(engine)
    found = {
        (table, tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]),
         fk["options"].get("ondelete", "NO ACTION"))
        for table in insp.get_table_names()
        for fk in insp.get_foreign_keys(table)
    }
    assert found == {
        ("background_job_logs", ("background_job_id",), "background_jobs", ("background_job_id",), "CASCADE"),
        ("jobs", ("background_job_id",), "background_jobs", ("background_job_id",), "NO ACTION"),
        ("candidates", ("background_job_id",), "background_jobs", ("background_job_id",), "NO ACTION"),
        ("job_skills", ("job_id",), "jobs", ("job_id",), "CASCADE"),
        ("job_skills", ("skill_id",), "skills", ("skill_id",), "NO ACTION"),
        ("candidate_skills", ("candidate_id",), "candidates", ("candidate_id",), "CASCADE"),
        ("candidate_skills", ("skill_id",), "skills", ("skill_id",), "NO ACTION"),
        ("matches", ("candidate_id",), "candidates", ("candidate_id",), "CASCADE"),
        ("matches", ("job_id",), "jobs", ("job_id",), "CASCADE"),
    }


def test_column_count_and_key_types(session):
    rows = session.execute(text(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
    )).all()
    types = {(t, c): d for t, c, d in rows}
    assert len(types) == 77  # every LLD column, nothing more
    assert types[("matches", "score")] == "double precision"
    assert types[("matches", "text_similarity")] == "double precision"
    for key in [("jobs", "job_id"), ("candidates", "candidate_id"), ("background_jobs", "background_job_id")]:
        assert types[key] == "uuid"
    assert types[("background_job_logs", "log_id")] == "bigint"
    assert types[("skills", "skill_id")] == "integer"
    for key in [("candidates", "education"), ("candidates", "parse_warnings"), ("matches", "matched_skills"),
                ("matches", "missing_skills"), ("matches", "score_breakdown"), ("background_jobs", "params"),
                ("background_job_logs", "context")]:
        assert types[key] == "jsonb"


def test_documented_indexes_exist(session):
    names = set(session.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")).scalars())
    assert {
        "ix_matches_candidate_id_score", "ix_matches_job_id_score", "ix_job_skills_skill_id",
        "ix_candidate_skills_skill_id", "ix_jobs_title_trgm", "ix_jobs_company_trgm", "ix_candidates_name_trgm",
        "ix_candidates_current_title_trgm", "ix_jobs_posted_date", "ix_jobs_location", "ix_candidates_city",
        "ix_background_jobs_status_created_at", "ix_background_job_logs_background_job_id_log_id",
        "uq_candidates_lower_email",
    } <= names


def test_trigram_index_is_used_for_substring_search(session):
    session.execute(text("SET LOCAL enable_seqscan = off"))
    plan = "\n".join(session.execute(text("EXPLAIN SELECT 1 FROM jobs WHERE title ILIKE '%python%'")).scalars())
    assert "ix_jobs_title_trgm" in plan


# --- Defaults ----------------------------------------------------------------------------------


def test_defaults_are_applied(session):
    job = make_job()
    background_job = BackgroundJob(type="crawl", status="queued")
    candidate = make_candidate()
    session.add_all([job, background_job, candidate])
    session.flush()
    match = make_match(candidate, job)
    log = BackgroundJobLog(background_job=background_job, level="INFO", message="Started")
    session.add_all([match, log])
    session.flush()
    for obj in (job, background_job, candidate, match, log):
        session.refresh(obj)

    assert job.job_id.version == 4  # Python uuid4
    assert job.job_type == "unknown" and job.is_remote is False
    assert job.created_at is not None and job.updated_at is not None
    assert candidate.created_at is not None and candidate.updated_at is not None
    assert (background_job.progress_current, background_job.items_succeeded, background_job.items_failed) == (0, 0, 0)
    assert background_job.cancel_requested is False and background_job.created_at is not None
    assert background_job.progress_total is None
    assert match.computed_at is not None and match.text_similarity is None
    assert log.created_at is not None


def test_updated_at_changes_on_orm_update(session):
    job = make_job()
    session.add(job)
    session.flush()
    session.execute(update(Job).where(Job.job_id == job.job_id).values(updated_at=func.now() - text("interval '1 day'")))
    session.refresh(job)
    before = job.updated_at
    job.title = "Senior Backend Developer"
    session.flush()
    session.refresh(job)
    assert job.updated_at > before


# --- Unique constraints and composite keys ----------------------------------------------------


def test_unique_dedup_key(session):
    session.add(make_job(dedup_key="https://jobs.example.com/a"))
    session.flush()
    error = integrity_error(session, make_job(dedup_key="https://jobs.example.com/a"))
    assert (error.sqlstate, error.diag.constraint_name) == (UNIQUE_VIOLATION, "uq_jobs_dedup_key")


def test_unique_file_sha256(session):
    session.add(make_candidate(file_sha256="abc123"))
    session.flush()
    error = integrity_error(session, make_candidate(file_sha256="abc123"))
    assert (error.sqlstate, error.diag.constraint_name) == (UNIQUE_VIOLATION, "uq_candidates_file_sha256")


def test_unique_canonical_name(session):
    _skill(session, "Python")
    error = integrity_error(session, Skill(canonical_name="Python"))
    assert (error.sqlstate, error.diag.constraint_name) == (UNIQUE_VIOLATION, "uq_skills_canonical_name")


def test_email_unique_ignoring_case_but_nulls_allowed(session):
    session.add_all([make_candidate(email="Asha@Example.com"), make_candidate(email=None), make_candidate(email=None)])
    session.flush()  # two candidates without email are fine (partial index)
    error = integrity_error(session, make_candidate(email="asha@example.COM"))
    assert (error.sqlstate, error.diag.constraint_name) == (UNIQUE_VIOLATION, "uq_candidates_lower_email")


def test_composite_primary_keys_reject_duplicate_pairs(session):
    job, candidate, skill = make_job(), make_candidate(), _skill(session, "Docker")
    session.add_all([job, candidate])
    session.flush()
    session.add_all([
        JobSkill(job=job, skill=skill, requirement_level="required"),
        CandidateSkill(candidate=candidate, skill=skill),
        make_match(candidate, job),
    ])
    session.flush()
    session.expunge_all()  # the duplicates below are new objects with the same keys

    cases = [
        (JobSkill(job_id=job.job_id, skill_id=skill.skill_id, requirement_level="nice_to_have"), "pk_job_skills"),
        (CandidateSkill(candidate_id=candidate.candidate_id, skill_id=skill.skill_id), "pk_candidate_skills"),
        (Match(candidate_id=candidate.candidate_id, job_id=job.job_id, score=10.0, matched_skills=[],
               missing_skills=[], explanation="x", score_breakdown={}), "pk_matches"),
    ]
    for duplicate, constraint in cases:
        error = integrity_error(session, duplicate)
        assert (error.sqlstate, error.diag.constraint_name) == (UNIQUE_VIOLATION, constraint)


# --- Check and NOT NULL constraints -------------------------------------------------------------


@pytest.mark.parametrize(
    ("factory", "constraint"),
    [
        (lambda s: make_job(job_type="freelance"), "ck_jobs_job_type"),
        (lambda s: make_job(salary_min=2000, salary_max=1000), "ck_jobs_salary_range"),
        (lambda s: make_job(min_experience_years=-1), "ck_jobs_min_experience_years_not_negative"),
        (lambda s: make_candidate(years_experience=-0.5), "ck_candidates_years_experience_not_negative"),
        (lambda s: BackgroundJob(type="export", status="queued"), "ck_background_jobs_type"),
        (lambda s: BackgroundJob(type="crawl", status="paused"), "ck_background_jobs_status"),
        (lambda s: BackgroundJob(type="crawl", status="queued", progress_current=-1),
         "ck_background_jobs_progress_current_not_negative"),
        (lambda s: JobSkill(job=make_job(), skill=_skill(s, "Go"), requirement_level="optional"),
         "ck_job_skills_requirement_level"),
        (lambda s: make_match(make_candidate(), make_job(), score=100.000001), "ck_matches_score_range"),
        (lambda s: make_match(make_candidate(), make_job(), score=-0.000001), "ck_matches_score_range"),
    ],
)
def test_check_constraints_reject_invalid_values(session, factory, constraint):
    error = integrity_error(session, factory(session))
    assert (error.sqlstate, error.diag.constraint_name) == (CHECK_VIOLATION, constraint)


def test_check_constraints_accept_boundary_values(session):
    job, candidate = make_job(salary_min=1000, salary_max=None, min_experience_years=0), make_candidate()
    session.add_all([
        job,
        make_job(salary_min=500, salary_max=500, job_type="internship"),
        candidate,
        make_match(candidate, job, score=0.0),
        make_match(candidate, make_job(), score=100.0),
        BackgroundJob(type="match", status="cancelled", progress_current=0),
    ])
    session.flush()


@pytest.mark.parametrize(
    ("factory", "column"),
    [
        (lambda: make_job(title=None), "title"),
        (lambda: make_job(apply_url=None), "apply_url"),
        (lambda: make_job(source=None), "source"),
        (lambda: make_job(dedup_key=None), "dedup_key"),
        (lambda: make_candidate(source_file=None), "source_file"),
        (lambda: make_candidate(parsed_with_ocr=None), "parsed_with_ocr"),
        (lambda: make_candidate(file_sha256=None), "file_sha256"),
        (lambda: Skill(canonical_name=None), "canonical_name"),
        (lambda: BackgroundJob(type=None, status="queued"), "type"),
        (lambda: BackgroundJob(type="crawl", status=None), "status"),
        (lambda: make_match(make_candidate(), make_job(), score=None), "score"),
        (lambda: make_match(make_candidate(), make_job(), explanation=None), "explanation"),
        (lambda: make_match(make_candidate(), make_job(), matched_skills=None), "matched_skills"),
        (lambda: make_match(make_candidate(), make_job(), missing_skills=None), "missing_skills"),
        (lambda: make_match(make_candidate(), make_job(), score_breakdown=None), "score_breakdown"),
    ],
)
def test_not_null_constraints(session, factory, column):
    error = integrity_error(session, factory())
    assert (error.sqlstate, error.diag.column_name) == (NOT_NULL_VIOLATION, column)


def test_python_none_in_jsonb_is_stored_as_sql_null(session):
    # Without none_as_null=True, SQLAlchemy would store the JSON value 'null' instead.
    candidate = make_candidate(education=None, parse_warnings=None)
    background_job = BackgroundJob(type="crawl", status="queued", params=None)
    session.add_all([candidate, background_job])
    session.flush()
    nulls = session.execute(
        text("SELECT education IS NULL, parse_warnings IS NULL FROM candidates WHERE candidate_id = :c"),
        {"c": candidate.candidate_id},
    ).one()
    assert tuple(nulls) == (True, True)
    assert session.execute(
        text("SELECT params IS NULL FROM background_jobs WHERE background_job_id = :b"),
        {"b": background_job.background_job_id},
    ).scalar() is True


# --- Cascade deletes (done in SQL, so the database's ON DELETE rules are what is tested) --------


def test_deleting_a_job_deletes_its_skill_links_and_matches(session):
    job, other_job, candidate, skill = make_job(), make_job(), make_candidate(), _skill(session, "SQL")
    session.add_all([job, other_job, candidate])
    session.flush()
    session.add_all([
        JobSkill(job=job, skill=skill, requirement_level="required"),
        make_match(candidate, job),
        make_match(candidate, other_job),
    ])
    session.flush()

    session.execute(delete(Job).where(Job.job_id == job.job_id))
    assert _count(session, JobSkill, job_id=job.job_id) == 0
    assert _count(session, Match, job_id=job.job_id) == 0
    assert _count(session, Match, job_id=other_job.job_id) == 1  # other matches untouched
    assert _count(session, Skill, skill_id=skill.skill_id) == 1  # the skill itself stays
    assert _count(session, Candidate, candidate_id=candidate.candidate_id) == 1


def test_deleting_a_candidate_deletes_its_skill_links_and_matches(session):
    job, candidate, skill = make_job(), make_candidate(), _skill(session, "React")
    session.add_all([job, candidate])
    session.flush()
    session.add_all([CandidateSkill(candidate=candidate, skill=skill), make_match(candidate, job)])
    session.flush()

    session.execute(delete(Candidate).where(Candidate.candidate_id == candidate.candidate_id))
    assert _count(session, CandidateSkill, candidate_id=candidate.candidate_id) == 0
    assert _count(session, Match, candidate_id=candidate.candidate_id) == 0
    assert _count(session, Job, job_id=job.job_id) == 1


def test_deleting_a_background_job_deletes_its_logs(session):
    background_job = BackgroundJob(type="resume", status="completed")
    session.add(background_job)
    session.flush()
    session.add_all([BackgroundJobLog(background_job=background_job, level="INFO", message=f"line {i}") for i in range(3)])
    session.flush()

    session.execute(delete(BackgroundJob).where(BackgroundJob.background_job_id == background_job.background_job_id))
    assert _count(session, BackgroundJobLog, background_job_id=background_job.background_job_id) == 0


def test_a_background_job_with_jobs_or_candidates_cannot_be_deleted(session):
    for record in (make_job, make_candidate):
        background_job = BackgroundJob(type="crawl", status="completed")
        session.add(background_job)
        session.flush()
        session.add(record(background_job_id=background_job.background_job_id))
        session.flush()
        error = integrity_error(
            session,
            statement=delete(BackgroundJob).where(BackgroundJob.background_job_id == background_job.background_job_id),
        )
        assert error.sqlstate == FK_VIOLATION


def test_a_skill_in_use_cannot_be_deleted(session):
    job, skill = make_job(), _skill(session, "Kubernetes")
    session.add(job)
    session.flush()
    session.add(JobSkill(job=job, skill=skill, requirement_level="nice_to_have"))
    session.flush()
    error = integrity_error(session, statement=delete(Skill).where(Skill.skill_id == skill.skill_id))
    assert (error.sqlstate, error.diag.constraint_name) == (FK_VIOLATION, "fk_job_skills_skill_id_skills")


def test_unknown_foreign_keys_are_rejected(session):
    import uuid

    error = integrity_error(session, BackgroundJobLog(background_job_id=uuid.uuid4(), level="INFO", message="x"))
    assert (error.sqlstate, error.diag.constraint_name) == (FK_VIOLATION, "fk_background_job_logs_background_job_id_background_jobs")


# --- Full-precision score storage -----------------------------------------------------------------


def test_scores_are_stored_and_read_back_at_full_precision(session):
    exact_scores = [
        float(Fraction(215, 3)),          # 71.666..., the worked example in HLD §10.9
        float(Fraction(100, 3)),          # 33.333...
        80.004,
        80.001,                           # both display as 80.00
        0.1 + 0.2,                        # 0.30000000000000004: a value a numeric(5,2) column would destroy
        float(Fraction(2, 3) * 10 + 70),  # 76.666...
    ]
    candidate = make_candidate()
    session.add(candidate)
    session.flush()
    jobs = [make_job() for _ in exact_scores]
    session.add_all(jobs)
    session.flush()
    session.add_all([make_match(candidate, job, score=score) for job, score in zip(jobs, exact_scores)])
    session.flush()
    session.expire_all()

    stored = session.execute(
        select(Match.job_id, Match.score).where(Match.candidate_id == candidate.candidate_id)
    ).all()
    by_job = {job_id: score for job_id, score in stored}
    for job, score in zip(jobs, exact_scores):
        assert type(by_job[job.job_id]) is float
        assert by_job[job.job_id] == score  # bit-for-bit, no rounding

    # The database's own text form also keeps every digit.
    as_text = session.execute(text("SELECT score::text FROM matches WHERE job_id = :j"), {"j": jobs[0].job_id}).scalar()
    assert float(as_text) == float(Fraction(215, 3)) and len(as_text) > 6


def test_ranking_uses_full_precision(session):
    candidate = make_candidate()
    high, low = make_job(title="Higher"), make_job(title="Lower")
    session.add_all([candidate, high, low])
    session.flush()
    # Same 2-decimal display value (80.00); the lower one has the better tie-breaker.
    session.add_all([
        make_match(candidate, high, score=80.004, text_similarity=0.10),
        make_match(candidate, low, score=80.001, text_similarity=0.99),
    ])
    session.flush()

    ranked = session.execute(
        select(Job.title)
        .join(Match, Match.job_id == Job.job_id)
        .where(Match.candidate_id == candidate.candidate_id)
        .order_by(Match.score.desc(), Match.text_similarity.desc())
    ).scalars().all()
    assert ranked == ["Higher", "Lower"]


# --- ORM relationships and log ordering ------------------------------------------------------------


def test_relationships_navigate_both_ways(session):
    background_job = BackgroundJob(type="crawl", status="running")
    python, docker = Skill(canonical_name="Python"), Skill(canonical_name="Docker")
    job = make_job(background_job=background_job)
    job.skills = [JobSkill(skill=python, requirement_level="required"),
                  JobSkill(skill=docker, requirement_level="nice_to_have")]
    candidate = make_candidate(background_job=background_job)
    candidate.skills = [CandidateSkill(skill=python)]
    session.add_all([job, candidate, make_match(candidate, job)])
    session.flush()
    session.expire_all()

    loaded = session.get(Job, job.job_id)
    assert loaded.background_job.background_job_id == background_job.background_job_id
    assert {(link.skill.canonical_name, link.requirement_level) for link in loaded.skills} == {
        ("Python", "required"), ("Docker", "nice_to_have")}
    assert [m.candidate.candidate_id for m in loaded.matches] == [candidate.candidate_id]
    parent = session.get(BackgroundJob, background_job.background_job_id)
    assert [j.job_id for j in parent.jobs] == [job.job_id]
    assert [c.candidate_id for c in parent.candidates] == [candidate.candidate_id]


def test_log_ids_increase_and_logs_load_in_order(session):
    background_job = BackgroundJob(type="crawl", status="running")
    session.add(background_job)
    session.flush()
    for i in range(5):
        session.add(BackgroundJobLog(background_job=background_job, level="INFO", message=f"line {i}"))
        session.flush()
    session.expire_all()
    logs = session.get(BackgroundJob, background_job.background_job_id).logs
    ids = [log.log_id for log in logs]
    assert ids == sorted(ids) and len(set(ids)) == 5
    assert [log.message for log in logs] == [f"line {i}" for i in range(5)]
