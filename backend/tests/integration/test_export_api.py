"""GET /exports/jobs, /exports/candidates and /exports/matches against PostgreSQL (LLD §4.6, §9.8; HLD §8.10).

The match table is produced by the real `match` task (run in this process), then read back through
the export and compared with the stored rows and with GET /candidates/{id}/matches. Search,
detail and export requests must never recompute or change a match. The people are invented.
"""

import csv
import io
import json
import re
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.db.session import SessionLocal
from app.main import app
from app.matching.explanation import display
from app.models import BackgroundJob, Match
from app.services import background_jobs as job_service
from app.services import export
from app.worker import tasks  # noqa: F401  (registers the tasks)
from app.worker.celery_app import celery_app
from tests.integration.helpers import insert_candidate, insert_job

PRIVATE_TEXT = "PRIVATE RESUME TEXT"
STORED_PATH = "6b1f2c3d-0000-4000-8000-000000000009.pdf"
FILENAME = r'attachment; filename="{entity}_\d{{4}}-\d\d-\d\dT\d\d-\d\d-\d\dZ\.{ext}"'


@pytest.fixture
def api(app_db, monkeypatch):
    """Publishing a task runs it at once, in this process."""
    monkeypatch.setattr(job_service, "publish_task",
                        lambda name, job_id: celery_app.tasks[name].apply(args=[str(job_id)]).id)
    monkeypatch.setattr(job_service, "revoke_task", lambda task_id: None)
    return TestClient(app)


@pytest.fixture
def data(app_db):
    jobs = {
        "backend": insert_job(title="Backend Python Developer", company='Acme, "Analytics"', location="Pune, India",
                              job_type="full_time", posted_date=date(2026, 11, 3), min_experience_years=Decimal(3),
                              salary_min=Decimal(900000), salary_max=Decimal(1400000), salary_currency="INR",
                              salary_period="year", description='Line one, with "quotes".\nLine two.',
                              required=["Python", "FastAPI", "PostgreSQL", "Docker"], nice=["Redis", "Kubernetes"]),
        "evil": insert_job(title='=HYPERLINK("http://evil.example","click")', company="+cmd|' /C calc'!A0",
                           location="-2+3", job_type="contract", posted_date=date(2026, 11, 5),
                           description="@SUM(A1:A9)", required=["Python"]),
        "react": insert_job(title="Frontend Engineer (React)", company="Globex", location="Bangalore",
                            job_type="full_time", posted_date=date(2026, 11, 1), min_experience_years=Decimal("1.5"),
                            required=["React"], nice=["TypeScript"]),
        "empty": insert_job(title="Office Manager", company="Initech", location="Mumbai", job_type="full_time"),
    }
    people = {
        "asha": insert_candidate(name="Asha Verma", current_title="Senior Backend Engineer", city="Pune",
                                 years_experience=Decimal(2), email="asha.verma@example.com", phone="+919876543210",
                                 resume_text=PRIVATE_TEXT + " Asha", stored_path=STORED_PATH,
                                 parse_warnings=["invalid phone removed"], source_file="asha_cv.pdf",
                                 education=[{"degree": "B.Tech", "institution": "Pune University", "years": "2013 - 2017"}],
                                 skills=["Python", "FastAPI", "PostgreSQL", "Redis", "Git"]),
        "evil": insert_candidate(name="@SUM(1+1)", current_title="-Engineer", city="Bengaluru",
                                 years_experience=Decimal("4.5"), source_file="=evil.pdf",
                                 resume_text=PRIVATE_TEXT + " react", skills=["React", "Python"]),
        "meera": insert_candidate(name="Meera Iyer", current_title="Frontend Developer", city="Chennai",
                                  skills=["TypeScript"]),
    }
    return jobs, people


def rows_of(response) -> list[list[str]]:
    assert response.status_code == 200, response.text
    return list(csv.reader(io.StringIO(response.content.decode("utf-8"), newline="")))


def as_dicts(response) -> list[dict]:
    header, *rows = rows_of(response)
    return [dict(zip(header, row, strict=True)) for row in rows]


def snapshot() -> list[tuple]:
    with SessionLocal() as session:
        return list(session.execute(text("SELECT candidate_id, job_id, score, score_breakdown::text, explanation, "
                                         "text_similarity, computed_at FROM matches ORDER BY 1, 2")).all())


def background_jobs() -> int:
    with SessionLocal() as session:
        return session.execute(select(func.count()).select_from(BackgroundJob)).scalar_one()


# --- Headers, formats, empty exports ---------------------------------------------------------------


@pytest.mark.parametrize("entity", ["jobs", "candidates", "matches"])
@pytest.mark.parametrize(("fmt", "media_type"), [("csv", "text/csv; charset=utf-8"), ("json", "application/json")])
def test_headers(api, data, entity, fmt, media_type):
    response = api.get(f"/exports/{entity}?format={fmt}")
    assert response.status_code == 200
    assert response.headers["content-type"] == media_type
    assert re.fullmatch(FILENAME.format(entity=entity, ext=fmt), response.headers["content-disposition"])
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(("path", "header"), [
    ("/exports/jobs?format=csv&skill=cobol", export.JOB_COLUMNS),
    ("/exports/candidates?format=csv&city=atlantis", export.CANDIDATE_COLUMNS),
    ("/exports/matches?format=csv", export.MATCH_COLUMNS),  # no match run yet: no rows
])
def test_empty_exports(api, data, path, header):
    assert rows_of(api.get(path)) == [header]
    assert api.get(path.replace("format=csv", "format=json")).json() == []


def test_empty_database(api, app_db):
    assert rows_of(api.get("/exports/jobs?format=csv")) == [export.JOB_COLUMNS]
    assert api.get("/exports/candidates?format=json").json() == []


# --- Jobs ------------------------------------------------------------------------------------------


def test_jobs_export_holds_what_the_search_shows(api, data):
    """Same filters, same order, every page: "what you see is what you export" (HLD §9.4)."""
    for query in ["", "skill=python", "sort=title", "sort=posted_date&order=asc", "q=engineer", "location=bangalore",
                  "max_required_years=2", "job_type=full_time&sort=title&order=desc"]:
        searched = [item["job_id"] for item in api.get(f"/jobs?{query}&page_size=100").json()["items"]]
        exported = [row["job_id"] for row in as_dicts(api.get(f"/exports/jobs?format=csv&{query}"))]
        as_json = [item["job_id"] for item in api.get(f"/exports/jobs?format=json&{query}").json()]
        assert exported == as_json == searched, query


def test_jobs_csv_columns_and_values(api, data):
    jobs, _ = data
    rows = {row["job_id"]: row for row in as_dicts(api.get("/exports/jobs?format=csv"))}
    backend = rows[str(jobs["backend"])]
    assert list(backend) == export.JOB_COLUMNS
    assert backend["company"] == 'Acme, "Analytics"'                         # commas and quotes survive
    assert backend["description"] == 'Line one, with "quotes".\nLine two.'   # so do line breaks
    assert backend["required_skills"] == "Docker; FastAPI; PostgreSQL; Python"
    assert backend["nice_to_have_skills"] == "Kubernetes; Redis"
    assert (backend["salary_min"], backend["salary_max"], backend["min_experience_years"]) == ("900000", "1400000", "3")
    assert backend["posted_date"] == "2026-11-03" and backend["is_remote"] == "false"
    assert rows[str(jobs["react"])]["min_experience_years"] == "1.5"
    assert rows[str(jobs["empty"])]["required_skills"] == "" and rows[str(jobs["empty"])]["posted_date"] == ""


def test_jobs_json_items_are_the_detail_responses(api, data):
    exported = api.get("/exports/jobs?format=json").json()
    assert exported == [api.get(f"/jobs/{item['job_id']}").json() for item in exported]


def test_formula_injection_is_neutralized_in_csv_only(api, data):
    jobs, people = data
    job = {row["job_id"]: row for row in as_dicts(api.get("/exports/jobs?format=csv"))}[str(jobs["evil"])]
    assert job["title"] == "'" + '=HYPERLINK("http://evil.example","click")'
    assert job["company"] == "'+cmd|' /C calc'!A0"
    assert job["location"] == "'-2+3" and job["description"] == "'@SUM(A1:A9)"
    person = {row["candidate_id"]: row for row in as_dicts(api.get("/exports/candidates?format=csv"))}[str(people["evil"])]
    assert (person["name"], person["current_title"], person["source_file"]) == ("'@SUM(1+1)", "'-Engineer", "'=evil.pdf")
    raw = {item["job_id"]: item for item in api.get("/exports/jobs?format=json").json()}[str(jobs["evil"])]
    assert raw["title"] == '=HYPERLINK("http://evil.example","click")'  # JSON keeps the data as it is


def test_export_streams_in_batches(api, data, monkeypatch):
    """A server-side cursor hands over a few rows at a time; the file is still complete and in order."""
    monkeypatch.setattr(export, "EXPORT_BATCH_ROWS", 1)
    expected = [item["job_id"] for item in api.get("/jobs?sort=title").json()["items"]]
    assert [row["job_id"] for row in as_dicts(api.get("/exports/jobs?format=csv&sort=title"))] == expected
    assert len(api.get("/exports/jobs?format=json").json()) == 4


# --- Candidates ------------------------------------------------------------------------------------


def test_candidates_export(api, data):
    _, people = data
    csv_rows = as_dicts(api.get("/exports/candidates?format=csv"))
    searched = api.get("/candidates?page_size=100").json()["items"]
    assert [row["candidate_id"] for row in csv_rows] == [item["candidate_id"] for item in searched]
    assert list(csv_rows[0]) == export.CANDIDATE_COLUMNS
    asha = {row["candidate_id"]: row for row in csv_rows}[str(people["asha"])]
    assert asha["skills"] == "FastAPI; Git; PostgreSQL; Python; Redis"
    assert asha["education"] == "B.Tech, Pune University (2013 - 2017)"
    assert (asha["years_experience"], asha["parsed_with_ocr"]) == ("2", "false")
    assert api.get("/exports/candidates?format=json").json() == searched  # the search items, all pages
    filtered = as_dicts(api.get("/exports/candidates?format=csv&skill=reactjs"))
    assert [row["candidate_id"] for row in filtered] == [str(people["evil"])]


@pytest.mark.parametrize("path", ["/exports/candidates?format=csv", "/exports/candidates?format=json",
                                  "/exports/matches?format=csv", "/exports/matches?format=json"])
def test_exports_expose_no_internal_data(api, data, path):
    api.post("/background-jobs/match")
    body = api.get(path).text
    for secret in (PRIVATE_TEXT, STORED_PATH, "resume_text", "stored_path", "file_sha256", "background_job_id",
                   "invalid phone removed"):
        assert secret not in body
    if "matches" in path:  # the match table names candidates; it has no contact details
        assert "asha.verma@example.com" not in body and "+919876543210" not in body


# --- The match table -------------------------------------------------------------------------------


def test_match_table_equals_the_stored_matches_and_the_api(api, data):
    _, people = data
    assert api.post("/background-jobs/match").status_code == 202
    exported = api.get("/exports/matches?format=json").json()
    csv_rows = as_dicts(api.get("/exports/matches?format=csv"))
    assert len(exported) == len(csv_rows) == 3 * 4  # 3 candidates, 4 jobs each (top 10 > 4)
    assert list(csv_rows[0]) == export.MATCH_COLUMNS

    with SessionLocal() as session:
        stored = {(str(m.candidate_id), str(m.job_id)): m for m in session.execute(select(Match)).scalars()}
    for item, row in zip(exported, csv_rows, strict=True):
        match = stored[(item["candidate_id"], item["job_id"])]
        assert item["score"] == display(match.score) and float(row["score"]) == item["score"]
        assert item["explanation"] == match.explanation == row["explanation"]
        assert item["matched_skills"] == match.matched_skills and item["missing_skills"] == match.missing_skills
        assert float(row["required_points"]) == item["breakdown"]["required"]["points"]
        assert float(row["location_points"]) == item["breakdown"]["location"]["points"]

    for person in people.values():  # each candidate's rows = GET /candidates/{id}/matches, in rank order
        api_items = api.get(f"/candidates/{person}/matches").json()["items"]
        mine = [item for item in exported if item["candidate_id"] == str(person)]
        assert [(i["rank"], i["job_id"], i["score"], i["breakdown"], i["text_similarity"], i["explanation"])
                for i in mine] == [(i["rank"], i["job_id"], i["score"], i["breakdown"], i["text_similarity"],
                                    i["explanation"]) for i in api_items]

    jobs, _ = data
    asha_rows = [r for r in csv_rows if r["candidate_id"] == str(people["asha"])]
    assert [r["rank"] for r in asha_rows] == ["1", "2", "3", "4"]
    # Rank 1 is the Python-only job: 70 + 15 (no nice-to-have list) + 10 (no minimum) + 0 (other city) = 95.
    assert (asha_rows[0]["job_id"], asha_rows[0]["score"]) == (str(jobs["evil"]), "95.0")
    worked = next(r for r in asha_rows if r["job_id"] == str(jobs["backend"]))
    assert worked["job_title"] == "Backend Python Developer" and worked["rank"] == "2"
    assert worked["matched_skills"] == "FastAPI (required); PostgreSQL (required); Python (required); Redis (nice-to-have)"
    assert worked["missing_skills"] == "Docker (required); Kubernetes (nice-to-have)"
    assert worked["score"] == "71.67"  # the worked example of LLD §7.11 (2 years, minimum 3, same city)
    assert worked["explanation"].startswith("Score 71.67/100. Has 3 of 4 required skills (52.50 pts; missing Docker).")


def test_match_table_top_and_candidate_filters(api, data):
    _, people = data
    api.post("/background-jobs/match")
    top_two = as_dicts(api.get("/exports/matches?format=csv&top=2"))
    order = [item["candidate_id"] for item in api.get("/candidates").json()["items"]]  # name order: @SUM.., Asha, Meera
    assert [(row["candidate_id"], row["rank"]) for row in top_two] == [(c, r) for c in order for r in ("1", "2")]
    pune = api.get("/exports/matches?format=json&city=pune&top=3").json()
    assert {item["candidate_id"] for item in pune} == {str(people["asha"])} and len(pune) == 3
    by_experience = as_dicts(api.get("/exports/matches?format=csv&top=1&sort=years_experience"))
    assert [row["candidate_id"] for row in by_experience] == [str(people["evil"]), str(people["asha"]),
                                                              str(people["meera"])]  # 4.5, 2, unknown last
    assert as_dicts(api.get("/exports/matches?format=csv&skill=cobol")) == []
    evil = next(r for r in top_two if r["candidate_id"] == str(people["evil"]))
    assert evil["candidate_name"] == "'@SUM(1+1)"  # formula protection in the match table too


@pytest.mark.parametrize("query", ["", "sort=name", "sort=name&order=asc", "sort=name&order=desc",
                                   "sort=years_experience", "sort=years_experience&order=desc",
                                   "sort=years_experience&order=asc", "skill=python&sort=years_experience&order=asc"])
def test_match_table_follows_the_documented_candidate_sort(api, data, query):
    """LLD §4.7: the match table's candidates come in the /candidates order for the same sort and order,
    each candidate's jobs by rank 1..top."""
    api.post("/background-jobs/match")
    candidates = [item["candidate_id"] for item in api.get(f"/candidates?{query}").json()["items"]]
    rows = as_dicts(api.get(f"/exports/matches?format=csv&top=2&{query}"))
    assert [(row["candidate_id"], row["rank"]) for row in rows] == [(c, r) for c in candidates for r in ("1", "2")]
    json_rows = api.get(f"/exports/matches?format=json&top=2&{query}").json()
    assert [(row["candidate_id"], row["rank"]) for row in json_rows] == [(c, r) for c in candidates for r in (1, 2)]


def test_match_table_sort_directions_differ_as_documented(api, data):
    _, people = data
    api.post("/background-jobs/match")
    order = lambda query: [r["candidate_id"] for r in as_dicts(api.get(f"/exports/matches?format=csv&top=1&{query}"))]  # noqa: E731
    # Years: "@SUM(1+1)" 4.5, Asha 2, Meera unknown (always last, in both directions).
    assert order("sort=years_experience") == names_of(people, "evil", "asha", "meera")           # default desc
    assert order("sort=years_experience&order=asc") == names_of(people, "asha", "evil", "meera")
    # Names (all set here): the default is A to Z, and desc is exactly the reverse. Where "@" sorts is
    # left to the database collation, so the names' own order is not written out.
    assert order("") == order("sort=name&order=asc")
    assert order("sort=name&order=desc") == list(reversed(order("sort=name&order=asc")))
    assert order("sort=name&order=asc").index(str(people["asha"])) < order("sort=name&order=asc").index(
        str(people["meera"]))


def names_of(people, *keys) -> list[str]:
    return [str(people[key]) for key in keys]


# --- Reading never recomputes or changes matches --------------------------------------------------


def test_search_detail_and_export_never_touch_matches(api, data, app_db):
    jobs, people = data
    api.post("/background-jobs/match")
    before, runs = snapshot(), background_jobs()
    requests = ["/jobs", "/jobs?skill=python&sort=title", f"/jobs/{jobs['backend']}", "/candidates",
                f"/candidates/{people['asha']}", "/skills", f"/candidates/{people['asha']}/matches",
                f"/jobs/{jobs['backend']}/matches", "/exports/jobs?format=csv", "/exports/candidates?format=json",
                "/exports/matches?format=csv", "/exports/matches?format=json&top=1"]
    statements: list[str] = []

    def record(conn, cursor, statement, *args):
        statements.append(statement.lstrip().split()[0].upper())

    from sqlalchemy import event
    event.listen(app_db, "before_cursor_execute", record)
    try:
        for path in requests:
            assert api.get(path).status_code == 200, path
    finally:
        event.remove(app_db, "before_cursor_execute", record)
    assert set(statements) <= {"SELECT", "DECLARE", "FETCH", "CLOSE", "BEGIN", "COMMIT", "ROLLBACK", "WITH"}
    assert snapshot() == before            # same scores, breakdowns, explanations and computed_at
    assert background_jobs() == runs       # no match run was started
    assert len(json.loads(api.get(f"/candidates/{people['asha']}/matches").text)["items"]) == 4  # top 10 limit intact
