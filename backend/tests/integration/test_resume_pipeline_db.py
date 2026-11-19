"""save_candidate against PostgreSQL: new, duplicate file, same email, skill links (LLD §3.6, §6.7)."""

import uuid

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models import BackgroundJob, Candidate, CandidateSkill, Skill
from app.resumes import pipeline
from app.resumes.pipeline import save_candidate
from app.schemas.candidate import validate_candidate


def record(**values):
    defaults = {"name": "Asha Verma", "email": "asha.verma@example.com", "phone": "+919876543210", "city": "Pune",
                "current_title": "Backend Engineer", "years_experience": 6, "skills": ["Python", "Go"],
                "education": [{"degree": "B.Tech", "institution": "Pune University", "years": "2013-2017"}],
                "summary": "Builds APIs.", "source_file": "cv_01.pdf", "parsed_with_ocr": False,
                "file_sha256": uuid.uuid4().hex + uuid.uuid4().hex, "stored_path": f"{uuid.uuid4()}.pdf",
                "resume_text": "Asha Verma resume text", "parse_warnings": []}
    return validate_candidate({**defaults, **values})


def save(rec, job_id=None):
    with SessionLocal() as session:
        outcome = save_candidate(session, rec, job_id)
        session.commit()
    return outcome


def a_job() -> uuid.UUID:
    with SessionLocal() as session:
        job = BackgroundJob(type="resume", status="running")
        session.add(job)
        session.commit()
        return job.background_job_id


def skills_of(candidate_id) -> list[str]:
    with SessionLocal() as session:
        return sorted(session.execute(
            select(Skill.canonical_name).join(CandidateSkill, CandidateSkill.skill_id == Skill.skill_id)
            .where(CandidateSkill.candidate_id == candidate_id)).scalars())


def count() -> int:
    with SessionLocal() as session:
        return session.scalar(select(func.count()).select_from(Candidate))


def test_a_new_candidate_is_saved_with_its_skills(app_db):
    job_id = a_job()
    rec = record(parse_warnings=["invalid phone removed"])
    outcome = save(rec, job_id)
    assert outcome.action == "created"
    with SessionLocal() as session:
        row = session.get(Candidate, outcome.candidate_id)
        assert (row.name, row.email, row.city, row.years_experience) == ("Asha Verma", "asha.verma@example.com", "Pune", 6)
        assert (row.source_file, row.stored_path, row.file_sha256) == (rec.source_file, rec.stored_path, rec.file_sha256)
        assert row.resume_text == "Asha Verma resume text" and row.parsed_with_ocr is False
        assert row.education == [{"degree": "B.Tech", "institution": "Pune University", "years": "2013-2017"}]
        assert row.parse_warnings == ["invalid phone removed"] and row.background_job_id == job_id
    assert skills_of(outcome.candidate_id) == ["Go", "Python"]


def test_the_same_file_is_a_duplicate_and_changes_nothing(app_db):
    first = save(record())
    again = save(record(file_sha256=_sha_of(first.candidate_id), name="Someone Else", email="other@example.com"))
    assert (again.action, again.candidate_id) == ("duplicate", first.candidate_id)
    assert count() == 1
    with SessionLocal() as session:
        assert session.get(Candidate, first.candidate_id).name == "Asha Verma"


def _sha_of(candidate_id) -> str:
    with SessionLocal() as session:
        return session.get(Candidate, candidate_id).file_sha256


def test_the_same_email_ignoring_case_updates_the_candidate(app_db):
    first = save(record(skills=["Python", "Go"]))
    job_id = a_job()
    newer = record(email="ASHA.Verma@Example.com", current_title="Staff Engineer", phone=None, skills=["Rust", "Python"],
                   source_file="cv_01_v2.pdf", parsed_with_ocr=True)
    outcome = save(newer, job_id)
    assert (outcome.action, outcome.candidate_id) == ("updated", first.candidate_id)
    assert count() == 1
    with SessionLocal() as session:
        row = session.get(Candidate, first.candidate_id)
        # The newer resume replaces the parsed fields, including fields it no longer has.
        assert (row.current_title, row.phone, row.source_file, row.parsed_with_ocr) == (
            "Staff Engineer", None, "cv_01_v2.pdf", True)
        assert (row.file_sha256, row.stored_path, row.background_job_id) == (
            newer.file_sha256, newer.stored_path, job_id)
        assert row.updated_at >= row.created_at
    assert skills_of(first.candidate_id) == ["Python", "Rust"]  # old links removed, new ones added


def test_candidates_without_an_email_are_never_merged(app_db):
    save(record(email=None))
    save(record(email=None))
    assert count() == 2


def test_a_file_saved_by_another_job_at_the_same_moment_is_a_duplicate(app_db, monkeypatch):
    """The duplicate check and the insert are not one step: the UNIQUE constraint decides, then the rules run again."""
    first = save(record())
    real = pipeline.find_by_file
    calls = []

    def stale_first_answer(session, sha256):
        calls.append(sha256)
        return None if len(calls) == 1 else real(session, sha256)
    monkeypatch.setattr(pipeline, "find_by_file", stale_first_answer)
    outcome = save(record(file_sha256=_sha_of(first.candidate_id), email="someone.else@example.com"))
    assert (outcome.action, outcome.candidate_id) == ("duplicate", first.candidate_id)
    assert count() == 1 and len(calls) == 2
