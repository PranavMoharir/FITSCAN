"""GET /jobs, /jobs/{id}, /candidates, /candidates/{id} and /skills against PostgreSQL (LLD §4.4-4.6, §9.8).

One small, fixed data set; every expected order is written out by hand. The people are invented.
"""

import uuid
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.db.session import SessionLocal
from app.main import app
from app.skills.sync import sync_skills
from app.skills.normalizer import get_taxonomy
from tests.integration.helpers import insert_candidate, insert_job

PRIVATE_TEXT = "PRIVATE RESUME TEXT of Asha"
STORED_PATH = "6b1f2c3d-0000-4000-8000-000000000001.pdf"
SHA = "a" * 64

JOB_KEYS = {"job_id", "title", "company", "location", "job_type", "salary", "posted_date", "required_skills",
            "nice_to_have_skills", "min_experience_years", "apply_url", "source"}
JOB_DETAIL_KEYS = JOB_KEYS | {"is_remote", "description", "salary_text", "source_url", "created_at", "updated_at"}
CANDIDATE_KEYS = {"candidate_id", "name", "email", "phone", "city", "current_title", "skills", "years_experience",
                  "education", "summary", "source_file", "parsed_with_ocr"}
CANDIDATE_DETAIL_KEYS = CANDIDATE_KEYS | {"parse_warnings", "created_at", "updated_at"}


@pytest.fixture
def api(app_db):
    return TestClient(app)


@pytest.fixture
def jobs(app_db) -> dict[str, uuid.UUID]:
    return {
        "backend": insert_job(title="Backend Python Developer", company="Acme Analytics", location="Pune, India",
                              job_type="full_time", posted_date=date(2026, 11, 3), min_experience_years=Decimal(3),
                              salary_min=Decimal(900000), salary_max=Decimal(1400000), salary_currency="INR",
                              salary_period="year", salary_text="₹9–14 lakh a year", description="APIs, with FastAPI.",
                              required=["Python", "FastAPI"], nice=["Docker"]),
        "frontend": insert_job(title="Frontend Engineer (React)", company="Globex", location="Bengaluru, India",
                               job_type="full_time", posted_date=date(2026, 11, 10), min_experience_years=Decimal(2),
                               required=["React", "TypeScript", "JavaScript"]),
        "analyst": insert_job(title="Data Analyst", company="Initrode", location="Remote", job_type="contract",
                              is_remote=True, min_experience_years=Decimal(1), required=["SQL", "Excel"], nice=["Python"]),
        "travel": insert_job(title="Senior Python Dev (50% travel)", company="Under_Score Ltd", location="Mumbai",
                             job_type="internship", posted_date=date(2026, 11, 1), required=["Python"]),
        "office": insert_job(title="office manager", company="acme logistics", location="Bangalore, Karnataka",
                             job_type="full_time", posted_date=date(2026, 11, 3), min_experience_years=Decimal(5)),
        "fresher": insert_job(title="Graduate Trainee", company="Hooli", location="Chennai, India (Hybrid)",
                              job_type="full_time", posted_date=date(2026, 11, 5), min_experience_years=Decimal(0),
                              required=["Git"]),
    }


@pytest.fixture
def people(app_db) -> dict[str, uuid.UUID]:
    return {
        "asha": insert_candidate(name="Asha Verma", current_title="Senior Backend Engineer", city="Pune",
                                 years_experience=Decimal(6), email="asha.verma@example.com", phone="+919876543210",
                                 resume_text=PRIVATE_TEXT, stored_path=STORED_PATH, file_sha256=SHA,
                                 parse_warnings=["invalid phone removed"], summary="Backend engineer.",
                                 education=[{"degree": "B.Tech", "institution": "Pune University", "years": "2013 - 2017"}],
                                 source_file="asha_cv.pdf", skills=["Python", "FastAPI", "Docker"]),
        "rahul": insert_candidate(name="rahul mehta", current_title="Data Analyst", city="Bengaluru",
                                  years_experience=Decimal("8.4"), skills=["SQL", "Excel", "Python"]),
        "meera": insert_candidate(name="Meera Iyer", current_title="Frontend Developer", city="Chennai",
                                  parsed_with_ocr=True, skills=["React", "TypeScript"]),
        "nameless": insert_candidate(name=None, current_title="QA Engineer", years_experience=Decimal(2),
                                     skills=["Pytest"]),
        "kiran": insert_candidate(name="Kiran Rao", current_title="Platform Engineer", city="Stewartbury",
                                  years_experience=Decimal("9.5"), skills=["Go"]),
    }


@contextmanager
def count_queries(engine):
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def ids(response, key="job_id") -> list[str]:
    assert response.status_code == 200, response.text
    return [item[key] for item in response.json()["items"]]


def names(jobs_or_people, *keys) -> list[str]:
    return [str(jobs_or_people[key]) for key in keys]


# --- GET /jobs -------------------------------------------------------------------------------------


def test_jobs_without_filters(api, jobs, app_db):
    """Default: newest first, jobs without a date last, equal dates by ID (LLD-5)."""
    with count_queries(app_db) as statements:
        body = api.get("/jobs").json()
    same_day = sorted([jobs["backend"], jobs["office"]])
    expected = [jobs["frontend"], jobs["fresher"], *same_day, jobs["travel"], jobs["analyst"]]
    assert [item["job_id"] for item in body["items"]] == [str(i) for i in expected]
    assert (body["total"], body["page"], body["page_size"]) == (6, 1, 20)
    assert len(statements) == 2  # count + page: skills come inside the page query


def test_job_item_shape(api, jobs):
    items = {item["job_id"]: item for item in api.get("/jobs").json()["items"]}
    backend = items[str(jobs["backend"])]
    assert set(backend) == JOB_KEYS
    assert backend["salary"] == {"min": 900000, "max": 1400000, "currency": "INR", "period": "year"}
    assert (backend["required_skills"], backend["nice_to_have_skills"]) == (["FastAPI", "Python"], ["Docker"])
    assert backend["min_experience_years"] == 3 and isinstance(backend["min_experience_years"], int)
    assert backend["posted_date"] == "2026-11-03" and backend["job_type"] == "full_time"
    office = items[str(jobs["office"])]
    assert office["salary"] is None and office["required_skills"] == office["nice_to_have_skills"] == []
    assert items[str(jobs["analyst"])]["posted_date"] is None


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("q=python", ["backend", "travel"]),
        ("q=PYTHON", ["backend", "travel"]),                    # case-insensitive
        ("q=acme", ["backend", "office"]),                      # the company is searched too
        ("q=50%25", ["travel"]),                                # % is a literal character, not a wildcard
        ("q=%25", ["travel"]),
        ("q=_", ["travel"]),                                    # so is _
        ("q=", ["backend", "frontend", "analyst", "travel", "office", "fresher"]),  # blank: no filter
        ("q=nothing-like-this", []),
        ("skill=js", ["frontend"]),                             # alias -> JavaScript
        ("skill=python", ["backend", "analyst", "travel"]),     # required or nice-to-have
        ("skill=Docker", ["backend"]),                          # a nice-to-have skill
        ("skill=reactjs", ["frontend"]),
        ("skill=cobol", []),                                    # not a skill of the taxonomy
        ("location=bangalore", ["frontend", "office"]),         # Bengaluru and Bangalore
        ("location=BENGALURU", ["frontend", "office"]),
        ("location=pune", ["backend"]),
        ("location=remote", ["analyst"]),
        ("location=hybrid", ["fresher"]),
        ("location=karna", ["office"]),                         # substring of the location
        ("job_type=contract", ["analyst"]),
        ("job_type=internship", ["travel"]),
        ("job_type=temporary", []),
        ("max_required_years=2", ["frontend", "analyst", "travel", "fresher"]),  # plus no minimum (LLD-6)
        ("max_required_years=0", ["travel", "fresher"]),
        ("max_required_years=2.5", ["frontend", "analyst", "travel", "fresher"]),
        ("max_required_years=50", ["backend", "frontend", "analyst", "travel", "office", "fresher"]),
        ("q=python&skill=docker", ["backend"]),
        ("skill=python&max_required_years=1", ["analyst", "travel"]),
        ("location=bangalore&job_type=full_time&max_required_years=4", ["frontend"]),
        ("q=python&location=mumbai&job_type=internship", ["travel"]),
        ("q=python&location=pune&job_type=contract", []),
    ],
)
def test_job_filters(api, jobs, query, expected):
    response = api.get(f"/jobs?{query}&page_size=100")
    assert sorted(ids(response)) == sorted(str(jobs[key]) for key in expected)
    assert response.json()["total"] == len(expected)


def test_job_sorting(api, jobs):
    titles = ["backend", "analyst", "frontend", "fresher", "office", "travel"]  # case-insensitive A-Z
    assert ids(api.get("/jobs?sort=title")) == names(jobs, *titles)
    assert ids(api.get("/jobs?sort=title&order=desc")) == names(jobs, *reversed(titles))
    same_day = [str(i) for i in sorted([jobs["backend"], jobs["office"]])]
    oldest_first = [str(jobs["travel"]), *same_day, str(jobs["fresher"]), str(jobs["frontend"]), str(jobs["analyst"])]
    assert ids(api.get("/jobs?sort=posted_date&order=asc")) == oldest_first  # no date: last in both directions


def test_job_pagination(api, jobs):
    everything = ids(api.get("/jobs"))
    pages = [api.get(f"/jobs?page={page}&page_size=4").json() for page in (1, 2, 3)]
    assert [len(p["items"]) for p in pages] == [4, 2, 0]
    assert all(p["total"] == 6 and p["page_size"] == 4 for p in pages)
    assert [item["job_id"] for p in pages for item in p["items"]] == everything  # no repeats, no gaps
    one_by_one = [ids(api.get(f"/jobs?page={page}&page_size=1"))[0] for page in range(1, 7)]
    assert one_by_one == everything
    assert api.get("/jobs?page=999").json() == {"items": [], "total": 6, "page": 999, "page_size": 20}
    assert len(ids(api.get("/jobs?page_size=100"))) == 6


def test_jobs_when_there_are_none(api, app_db):
    assert api.get("/jobs").json() == {"items": [], "total": 0, "page": 1, "page_size": 20}


# --- GET /jobs/{id} --------------------------------------------------------------------------------


def test_job_detail(api, jobs, app_db):
    with count_queries(app_db) as statements:
        response = api.get(f"/jobs/{jobs['backend']}")
    assert response.status_code == 200
    detail = response.json()
    assert set(detail) == JOB_DETAIL_KEYS
    assert len(statements) == 1  # the job with both skill lists, in one query
    assert detail["title"] == "Backend Python Developer" and detail["is_remote"] is False
    assert (detail["required_skills"], detail["nice_to_have_skills"]) == (["FastAPI", "Python"], ["Docker"])
    assert detail["description"] == "APIs, with FastAPI." and detail["salary_text"] == "₹9–14 lakh a year"
    assert api.get(f"/jobs/{jobs['analyst']}").json()["is_remote"] is True
    listed = next(i for i in api.get("/jobs").json()["items"] if i["job_id"] == str(jobs["backend"]))
    assert {key: detail[key] for key in JOB_KEYS} == listed  # the detail extends the list item


def test_job_detail_errors(api, jobs):
    unknown = api.get(f"/jobs/{uuid.uuid4()}")
    assert unknown.status_code == 404 and unknown.json() == {"error": {"code": "NOT_FOUND", "message": "Job not found."}}
    assert api.get("/jobs/not-a-uuid").status_code == 422


# --- GET /candidates -------------------------------------------------------------------------------


def test_candidates_without_filters(api, people, app_db):
    """Default: name A to Z, ignoring case; no name last."""
    with count_queries(app_db) as statements:
        body = api.get("/candidates").json()
    assert [i["candidate_id"] for i in body["items"]] == names(people, "asha", "kiran", "meera", "rahul", "nameless")
    assert body["total"] == 5
    assert len(statements) == 2


def test_candidate_item_shape_and_privacy(api, people):
    response = api.get("/candidates")
    asha = next(i for i in response.json()["items"] if i["candidate_id"] == str(people["asha"]))
    assert set(asha) == CANDIDATE_KEYS
    assert asha["skills"] == ["Docker", "FastAPI", "Python"]
    assert asha["years_experience"] == 6
    assert asha["education"] == [{"degree": "B.Tech", "institution": "Pune University", "years": "2013 - 2017"}]
    assert (asha["email"], asha["phone"], asha["source_file"]) == ("asha.verma@example.com", "+919876543210",
                                                                   "asha_cv.pdf")  # the approved contract fields
    for secret in (PRIVATE_TEXT, STORED_PATH, SHA, "resume_text", "stored_path", "file_sha256", "background_job_id",
                   "parse_warnings", "invalid phone removed"):
        assert secret not in response.text


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("q=engineer", ["asha", "kiran", "nameless"]),          # the current title is searched
        ("q=VERMA", ["asha"]),                                  # and the name, ignoring case
        ("q=analyst", ["rahul"]),
        ("q=%20%20", ["asha", "kiran", "meera", "rahul", "nameless"]),
        ("skill=reactjs", ["meera"]),
        ("skill=python", ["asha", "rahul"]),
        ("skill=Go", ["kiran"]),
        ("skill=cobol", []),
        ("city=bangalore", ["rahul"]),                          # a candidate in Bengaluru
        ("city=PUNE", ["asha"]),
        ("city=stewartbury", ["kiran"]),                        # a city that is not in the list
        ("city=atlantis", []),
        ("q=engineer&skill=python", ["asha"]),
        ("city=bengaluru&skill=sql", ["rahul"]),
        ("q=engineer&city=chennai", []),
    ],
)
def test_candidate_filters(api, people, query, expected):
    response = api.get(f"/candidates?{query}")
    assert ids(response, "candidate_id") == names(people, *expected)  # in the default name order
    assert response.json()["total"] == len(expected)


def test_candidate_sorting_by_experience(api, people):
    """Years unknown: last in both directions (LLD-5). /candidates has no experience filter (LLD-6)."""
    assert ids(api.get("/candidates?sort=years_experience"), "candidate_id") == names(
        people, "kiran", "rahul", "asha", "nameless", "meera")
    assert ids(api.get("/candidates?sort=years_experience&order=asc"), "candidate_id") == names(
        people, "nameless", "asha", "rahul", "kiran", "meera")
    assert ids(api.get("/candidates?sort=name&order=desc"), "candidate_id") == names(
        people, "rahul", "meera", "kiran", "asha", "nameless")


def test_candidate_pagination(api, people):
    everything = ids(api.get("/candidates"), "candidate_id")
    pages = [api.get(f"/candidates?page={page}&page_size=2").json() for page in (1, 2, 3, 4)]
    assert [len(p["items"]) for p in pages] == [2, 2, 1, 0]
    assert [i["candidate_id"] for p in pages for i in p["items"]] == everything
    assert all(p["total"] == 5 for p in pages)


# --- GET /candidates/{id} --------------------------------------------------------------------------


def test_candidate_detail(api, people, app_db):
    with count_queries(app_db) as statements:
        response = api.get(f"/candidates/{people['asha']}")
    detail = response.json()
    assert response.status_code == 200 and set(detail) == CANDIDATE_DETAIL_KEYS
    assert len(statements) == 1
    assert detail["parse_warnings"] == ["invalid phone removed"] and detail["skills"] == ["Docker", "FastAPI", "Python"]
    for secret in (PRIVATE_TEXT, STORED_PATH, SHA, "resume_text", "stored_path", "file_sha256", "background_job_id"):
        assert secret not in response.text
    assert api.get(f"/candidates/{people['meera']}").json()["parsed_with_ocr"] is True
    assert api.get(f"/candidates/{people['nameless']}").json()["parse_warnings"] == []


def test_candidate_detail_errors(api, people):
    unknown = api.get(f"/candidates/{uuid.uuid4()}")
    assert unknown.status_code == 404
    assert unknown.json() == {"error": {"code": "NOT_FOUND", "message": "Candidate not found."}}
    assert api.get("/candidates/12345").status_code == 422


# --- GET /skills -----------------------------------------------------------------------------------


def test_skills_are_all_on_one_page(api, app_db):
    with SessionLocal() as session:
        sync_skills(session)
        session.commit()
    body = api.get("/skills").json()
    taxonomy = get_taxonomy()
    assert body["total"] == len(taxonomy.canonical_names) == len(body["items"]) == body["page_size"]
    assert body["page"] == 1
    names_shown = [item["skill"] for item in body["items"]]
    assert names_shown == sorted(taxonomy.canonical_names, key=lambda n: (n.lower(), n))
    assert all(item["category"] == taxonomy.categories[item["skill"]] for item in body["items"])
    assert set(body["items"][0]) == {"skill", "category"}  # no aliases (LLD-2)
