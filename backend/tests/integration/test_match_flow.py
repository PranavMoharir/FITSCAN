"""End to end against PostgreSQL: POST /background-jobs/match -> `match` task -> matches table -> top-10 routes (LLD §9.8).

Celery runs the real `match` task in this process (`Task.apply`), so the API, the task, the
engine and the database run exactly as in production, without Redis. The people are invented.
"""

import random
import threading
import time
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update

from app.db.session import SessionLocal
from app.main import app
from app.matching import engine as match_engine
from app.matching.ranking import rank_key
from app.models import BackgroundJob, BackgroundJobLog, CandidateSkill, JobSkill, Match
from app.services import background_jobs as service
from app.skills.sync import skill_ids
from app.worker import tasks
from app.worker.celery_app import celery_app
from tests.integration.helpers import make_candidate, make_job

WORKED_SENTENCE = ("Score 71.67/100. Has 3 of 4 required skills (52.50 pts; missing Docker). Has 1 of 2 nice-to-have "
                   "skills (7.50 pts; missing Kubernetes). 2 years of experience against a 3-year minimum (6.67 pts). "
                   "Same city, Pune (5.00 pts).")
PRIVATE = ["Ananya", "Kulkarni", "Vikram", "Rathore", "ananya@", "vikram@"]
DEFAULT_WEIGHTS = {"required": 70, "nice": 15, "experience": 10, "location": 5}


@pytest.fixture
def env(app_db, monkeypatch):
    """Publishing runs the task at once, or keeps it for later with run_later=True."""
    state = {"run_later": False, "queued": []}

    def publish(name, job_id):
        if state["run_later"]:
            state["queued"].append((name, job_id))
            return "task-later"
        return celery_app.tasks[name].apply(args=[str(job_id)]).id

    monkeypatch.setattr(service, "publish_task", publish)
    monkeypatch.setattr(service, "revoke_task", lambda task_id: None)
    state["api"] = TestClient(app)
    return state


def add_job(*, required=(), nice=(), minimum=None, location="Pune, India", remote=False, title="Developer",
            company="Acme", description=None) -> uuid.UUID:
    with SessionLocal() as session:
        job = make_job(title=title, company=company, location=location, is_remote=remote, description=description,
                       min_experience_years=None if minimum is None else Decimal(str(minimum)))
        session.add(job)
        session.flush()
        ids = skill_ids(session, [*required, *nice])
        session.add_all([JobSkill(job_id=job.job_id, skill_id=ids[n], requirement_level="required") for n in required])
        session.add_all([JobSkill(job_id=job.job_id, skill_id=ids[n], requirement_level="nice_to_have") for n in nice])
        session.commit()
        return job.job_id


def add_candidate(*, skills=(), years=None, city="Pune", name="Test Person", title="Engineer", resume=None,
                  email=None) -> uuid.UUID:
    with SessionLocal() as session:
        person = make_candidate(name=name, current_title=title, city=city, resume_text=resume, email=email,
                                years_experience=None if years is None else Decimal(str(years)))
        session.add(person)
        session.flush()
        ids = skill_ids(session, skills)
        session.add_all([CandidateSkill(candidate_id=person.candidate_id, skill_id=ids[n]) for n in skills])
        session.commit()
        return person.candidate_id


def start_match(env, weights: dict | None = None) -> uuid.UUID:
    response = env["api"].post("/background-jobs/match", json={"weights": weights} if weights else None)
    assert response.status_code == 202, response.text
    return uuid.UUID(response.json()["background_job_id"])


def job_row(job_id) -> BackgroundJob:
    with SessionLocal() as session:
        return session.get(BackgroundJob, job_id)


def messages(job_id) -> list[str]:
    with SessionLocal() as session:
        return list(session.execute(select(BackgroundJobLog.message).where(BackgroundJobLog.background_job_id == job_id)
                                    .order_by(BackgroundJobLog.log_id)).scalars())


def stored() -> dict[tuple[uuid.UUID, uuid.UUID], Match]:
    with SessionLocal() as session:
        return {(m.candidate_id, m.job_id): m for m in session.execute(select(Match)).scalars()}


def snapshot() -> list[tuple]:
    with SessionLocal() as session:
        return list(session.execute(text("SELECT candidate_id, job_id, score, explanation, computed_at FROM matches "
                                         "ORDER BY 1, 2")).all())


def worked_example() -> tuple[uuid.UUID, uuid.UUID]:
    job = add_job(required=["Python", "FastAPI", "PostgreSQL", "Docker"], nice=["Redis", "Kubernetes"], minimum=3,
                  location="Pune, India", title="Backend Python Developer", company="Acme Analytics")
    person = add_candidate(skills=["Python", "FastAPI", "PostgreSQL", "Redis", "Git"], years=2, city="Pune")
    return person, job


# --- The run ---------------------------------------------------------------------------------------


def test_match_run_scores_and_stores_every_pair(env):
    person, worked = worked_example()
    others = [add_job(required=["Java"], location="Mumbai"), add_job(), add_job(nice=["Redis"], remote=True)]
    people = [person, add_candidate(skills=["Java"], years=1, city="Mumbai"), add_candidate()]

    job_id = start_match(env)
    row = job_row(job_id)
    assert (row.type, row.status, row.error_message) == ("match", "completed", None)
    assert (row.progress_current, row.progress_total, row.items_succeeded, row.items_failed) == (3, 3, 3, 0)
    assert row.params == {"weights": DEFAULT_WEIGHTS}  # every run records the weights it used (LLD §7.4)

    matches = stored()
    assert len(matches) == 3 * 4
    assert set(matches) == {(c, j) for c in people for j in [worked, *others]}
    assert len({m.computed_at for m in matches.values()}) == 1  # one run, one timestamp
    assert all(0 <= m.score <= 100 for m in matches.values())

    pair = matches[(person, worked)]
    assert pair.score == 71.66666666666667  # exactly 215/3, unrounded
    assert pair.explanation == WORKED_SENTENCE
    assert pair.score_breakdown["experience"]["points"] == 20 / 3
    assert pair.matched_skills == [{"skill": "FastAPI", "level": "required"}, {"skill": "PostgreSQL", "level": "required"},
                                   {"skill": "Python", "level": "required"}, {"skill": "Redis", "level": "nice_to_have"}]
    assert pair.missing_skills == [{"skill": "Docker", "level": "required"}, {"skill": "Kubernetes", "level": "nice_to_have"}]

    log = messages(job_id)
    assert "Matching started: 3 candidates × 4 jobs (12 pairs)." in log
    assert "1 of 4 jobs have no identified skills: they score R = 0 and N = 0, so at most 15 points." in log
    assert any(line.startswith("Saved 12 matches for 3 candidates; computed at ") for line in log)


def test_o2_and_other_edge_cases_are_stored(env):
    person = add_candidate(skills=["Python", "Docker"], years=5, city="Bengaluru")
    empty = add_job(location="Bengaluru")                       # no skills at all
    no_nice = add_job(required=["Python", "Docker"], location="Mumbai")
    only_nice = add_job(nice=["Docker", "AWS"], location="Bangalore, Karnataka")
    start_match(env)
    matches = stored()

    o2 = matches[(person, empty)]
    assert o2.score == 15.0
    assert o2.score_breakdown["required"]["rule"] == o2.score_breakdown["nice_to_have"]["rule"] == "no_skills_identified"
    assert "No required or nice-to-have skills could be identified for this job" in o2.explanation

    assert matches[(person, no_nice)].score_breakdown["nice_to_have"] == {
        "matched": 0, "total": 0, "ratio": 1.0, "points": 15.0, "rule": "none_listed"}
    assert matches[(person, no_nice)].score == 70 + 15 + 10 + 0

    kept = matches[(person, only_nice)]
    assert kept.score_breakdown["required"]["rule"] == "no_required_identified"
    assert kept.score == 0 + 7.5 + 10 + 5  # Bangalore and Bengaluru are the same city
    assert kept.score_breakdown["location"]["rule"] == "same_city"


def test_rerun_replaces_every_row(env):
    person, worked = worked_example()
    add_job(required=["Go"])
    start_match(env)
    first = stored()
    with SessionLocal() as session:  # the candidate learns Docker: the next run must see it
        session.add(CandidateSkill(candidate_id=person, skill_id=skill_ids(session, ["Docker"])["Docker"]))
        session.commit()
    second_job = start_match(env)
    second = stored()

    assert job_row(second_job).status == "completed"
    assert set(first) == set(second) and len(second) == 2
    assert second[(person, worked)].score > first[(person, worked)].score
    assert {m.computed_at for m in second.values()} != {m.computed_at for m in first.values()}
    with SessionLocal() as session:
        assert session.execute(select(func.count()).select_from(Match)).scalar_one() == 2


def test_new_candidates_and_jobs_are_matched_only_after_a_rerun(env):
    person, _ = worked_example()
    start_match(env)
    newcomer = add_candidate(skills=["Python"])
    response = env["api"].get(f"/candidates/{newcomer}/matches")
    assert response.status_code == 200
    assert response.json() == {"candidate_id": str(newcomer), "computed_at": None, "items": []}
    start_match(env)
    assert len(env["api"].get(f"/candidates/{newcomer}/matches").json()["items"]) == 1
    assert len(stored()) == 2


# --- Failure, cancellation, no data ------------------------------------------------------------------


def test_cancelled_run_leaves_previous_matches_unchanged(env):
    worked_example()
    add_candidate(skills=["Go"])
    start_match(env)
    before = snapshot()

    env["run_later"] = True
    job_id = start_match(env)
    with SessionLocal() as session:  # the user asks to stop before the worker even starts the first item
        session.execute(update(BackgroundJob).where(BackgroundJob.background_job_id == job_id).values(cancel_requested=True))
        session.commit()
    name, queued_id = env["queued"].pop()
    celery_app.tasks[name].apply(args=[str(queued_id)])

    row = job_row(job_id)
    assert row.status == "cancelled"
    assert row.progress_current == 1  # stopped after the first candidate
    assert "Cancelled by user after 1 items. The previous matches are unchanged." in messages(job_id)
    assert snapshot() == before


@pytest.mark.parametrize(("missing", "reason"), [("candidates", "No candidates to match: upload resumes first."),
                                                 ("jobs", "No jobs to match: run a crawl first.")])
def test_nothing_to_match_fails_with_a_reason(env, missing, reason):
    if missing == "jobs":
        add_candidate(skills=["Python"])
    else:
        add_job(required=["Python"])
    job_id = start_match(env)
    row = job_row(job_id)
    assert (row.status, row.error_message) == ("failed", reason)
    assert stored() == {}


def test_one_failing_candidate_does_not_stop_the_others(env, monkeypatch):
    person, worked = worked_example()
    broken = add_candidate(skills=["Go"], name="Vikram Rathore", email="vikram@example.org")
    real = tasks.score_candidate

    def score(candidate, jobs, similarities, weights):
        if candidate.candidate_id == broken:
            raise KeyError("Vikram Rathore")  # an exception message that quotes personal data
        return real(candidate, jobs, similarities, weights)

    monkeypatch.setattr(tasks, "score_candidate", score)
    job_id = start_match(env)
    row = job_row(job_id)
    assert (row.status, row.items_succeeded, row.items_failed) == ("completed", 1, 1)
    assert set(stored()) == {(person, worked)}
    log = messages(job_id)
    assert f"Candidate {str(broken)[:8]}: scoring failed (KeyError); it has no matches in this run." in log
    assert not [line for line in log if any(word in line for word in PRIVATE)]


def test_all_candidates_failing_keeps_the_previous_matches(env, monkeypatch):
    worked_example()
    start_match(env)
    before = snapshot()

    def fail(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(tasks, "score_candidate", fail)
    job_id = start_match(env)
    assert (job_row(job_id).status, job_row(job_id).error_message) == ("failed", "All 1 candidate failed.")
    assert snapshot() == before


def test_heartbeat_is_written_just_before_the_final_write(env, monkeypatch):
    worked_example()
    calls = []
    real_heartbeat, real_save = tasks.JobRun.heartbeat, tasks.save_matches
    monkeypatch.setattr(tasks.JobRun, "heartbeat", lambda self: (calls.append("heartbeat"), real_heartbeat(self))[1])
    monkeypatch.setattr(tasks, "save_matches", lambda session, rows: (calls.append("save"), real_save(session, rows))[1])
    start_match(env)
    assert calls == ["heartbeat", "save"]


def test_two_runs_saving_at_the_same_time_do_not_collide(env):
    """The EXCLUSIVE lock makes the second save wait, then replace the first one's rows."""
    person, worked = worked_example()
    with SessionLocal() as session:
        jobs, candidates = match_engine.load_inputs(session)
    rows = match_engine.score_candidate(candidates[0], jobs, [0.25], tasks.Weights.from_settings(
        tasks.get_settings().match_weights))
    second_rows = [match_engine.MatchRow(**{**row.__dict__, "text_similarity": 0.75}) for row in rows]

    first = SessionLocal()
    match_engine.save_matches(first, rows)  # holds the lock, not committed yet
    errors = []

    def second_save():
        with SessionLocal() as session:
            try:
                session.execute(text("SET lock_timeout = '20s'"))
                match_engine.save_matches(session, second_rows)
                session.commit()
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)

    thread = threading.Thread(target=second_save)
    thread.start()
    thread.join(timeout=1.0)
    assert thread.is_alive()  # waiting for the lock
    first.commit()
    first.close()
    thread.join(timeout=20)
    assert not thread.is_alive() and errors == []
    assert [m.text_similarity for m in stored().values()] == [0.75]


# --- An older run never overwrites a newer run's results (LLD §7.9) ---------------------------------
#
# "Newer" = claimed later (later started_at), so it loaded newer data. The tests hold runs just
# before they save, at the heartbeat written right before the final write, to force each order.


def run_task(job_id: uuid.UUID) -> str:
    """Run one queued match task in this thread and return its result ("completed", "cancelled", ...)."""
    return celery_app.tasks["match"].apply(args=[str(job_id)]).get()


def run_in_thread(job_id: uuid.UUID, results: dict) -> threading.Thread:
    thread = threading.Thread(target=lambda: results.__setitem__(job_id, run_task(job_id)))
    thread.start()
    return thread


def wait_for(condition, timeout: float = 20.0) -> None:
    end = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < end, "timed out"
        time.sleep(0.02)


class Gate:
    """Holds chosen runs at the heartbeat just before their final write, until released."""

    def __init__(self, monkeypatch):
        self.reached: dict[uuid.UUID, threading.Event] = {}
        self.go: dict[uuid.UUID, threading.Event] = {}
        real = tasks.JobRun.heartbeat
        gate = self

        def heartbeat(run):
            if run.job_id in gate.go:
                gate.reached[run.job_id].set()
                assert gate.go[run.job_id].wait(30)
            return real(run)

        monkeypatch.setattr(tasks.JobRun, "heartbeat", heartbeat)

    def hold(self, *job_ids: uuid.UUID) -> None:
        for job_id in job_ids:
            self.reached[job_id], self.go[job_id] = threading.Event(), threading.Event()


def saved_by() -> set:
    """The computed_at of the stored rows; it equals the finished_at of the run that saved them."""
    return {m.computed_at for m in stored().values()}


def saver_of_stored_rows() -> uuid.UUID:
    """The run whose "Saved … computed at T." log line names the stored rows' computed_at."""
    (computed_at,) = saved_by()
    with SessionLocal() as session:
        runs = session.execute(select(BackgroundJobLog.background_job_id).where(
            BackgroundJobLog.message.like(f"Saved %; computed at {computed_at.isoformat()}."))).scalars().all()
    assert len(runs) == 1, runs
    return runs[0]


def test_older_run_saving_last_does_not_overwrite_a_newer_run(env, monkeypatch):
    person, worked = worked_example()
    env["run_later"] = True
    older, newer = start_match(env), start_match(env)
    gate = Gate(monkeypatch)
    gate.hold(older)
    results: dict = {}
    thread = run_in_thread(older, results)
    assert gate.reached[older].wait(30)  # claimed, loaded (1 job) and scored; now waiting to save
    added = add_job(required=["Python"], title="Added after the older run loaded")
    results[newer] = run_task(newer)     # claimed later, loads 2 jobs, saves and completes
    gate.go[older].set()
    thread.join(30)

    assert results == {older: "cancelled", newer: "completed"}
    old_run, new_run = job_row(older), job_row(newer)
    assert old_run.started_at < new_run.started_at
    assert old_run.error_message == (f"Superseded: a newer match run (#{str(newer)[:8]}) saved its results first; "
                                     "these results were not saved.")
    assert set(stored()) == {(person, worked), (person, added)}  # the newer run's rows, with the added job
    assert saved_by() == {new_run.finished_at}
    log = messages(older)
    assert not [line for line in log if line.startswith("Saved ")]
    assert f"{old_run.error_message} The current matches are from that run." in log


def test_newer_run_saving_after_an_older_run_replaces_its_results(env, monkeypatch):
    person, worked = worked_example()
    env["run_later"] = True
    older, newer = start_match(env), start_match(env)
    gate = Gate(monkeypatch)
    gate.hold(older, newer)
    results: dict = {}
    older_thread = run_in_thread(older, results)
    assert gate.reached[older].wait(30)
    added = add_job(required=["Python"], title="Added after the older run loaded")
    newer_thread = run_in_thread(newer, results)
    assert gate.reached[newer].wait(30)  # both runs have loaded their data and wait to save

    gate.go[older].set()                 # the older run saves first: no newer run has completed yet
    older_thread.join(30)
    assert results[older] == "completed" and set(stored()) == {(person, worked)}
    gate.go[newer].set()
    newer_thread.join(30)

    assert results == {older: "completed", newer: "completed"}
    assert set(stored()) == {(person, worked), (person, added)}
    assert saved_by() == {job_row(newer).finished_at}


def test_runs_saving_at_the_same_time_always_keep_the_later_started_runs_results(env, monkeypatch):
    """Both runs in flight together; the save order alternates. The stored rows are always the newer run's."""
    worked_example()
    env["run_later"] = True
    rng = random.Random(11)
    delays: dict = {}
    real = tasks.JobRun.heartbeat
    monkeypatch.setattr(tasks.JobRun, "heartbeat", lambda run: (time.sleep(delays.get(run.job_id, 0)), real(run))[1])
    outcomes = []
    for round_number in range(6):
        older, newer = start_match(env), start_match(env)
        older_saves_first = round_number % 2 == 0
        delays[older] = (0.0 if older_saves_first else 1.0) + rng.uniform(0, 0.05)
        delays[newer] = (1.0 if older_saves_first else 0.0) + rng.uniform(0, 0.05)
        results: dict = {}
        older_thread = run_in_thread(older, results)
        wait_for(lambda: job_row(older).status != "queued")  # the older run is claimed first
        newer_thread = run_in_thread(newer, results)
        older_thread.join(30)
        newer_thread.join(30)

        assert job_row(older).started_at < job_row(newer).started_at
        assert saver_of_stored_rows() == newer, f"round {round_number}: the older run's rows are stored"
        assert results[newer] == "completed"
        outcomes.append(results[older])
    # The older run completes when it saves first and is superseded when it would save last.
    assert outcomes == ["completed", "cancelled"] * 3


def test_run_that_stopped_running_before_saving_writes_nothing(env, monkeypatch):
    """Saving and completing are one transaction: a run the stale-job check failed meanwhile saves nothing."""
    worked_example()
    add_candidate(skills=["Go"])
    start_match(env)
    before = snapshot()
    env["run_later"] = True
    job_id = start_match(env)
    real_save = tasks.save_matches

    def stale_check_then_save(session, rows):
        with SessionLocal() as other:  # the stale-job check, in another connection, while this run saves
            other.execute(update(BackgroundJob).where(BackgroundJob.background_job_id == job_id)
                          .values(status="failed", finished_at=func.now(), error_message="Worker stopped unexpectedly."))
            other.commit()
        return real_save(session, rows)

    monkeypatch.setattr(tasks, "save_matches", stale_check_then_save)
    assert run_task(job_id) == "not-running"
    assert snapshot() == before
    row = job_row(job_id)
    assert (row.status, row.error_message) == ("failed", "Worker stopped unexpectedly.")
    assert not [line for line in messages(job_id) if line.startswith("Saved ")]


def test_match_job_logs_contain_no_personal_data(env):
    add_candidate(skills=["Python"], name="Ananya Kulkarni", email="ananya@example.org", resume="Ananya Kulkarni")
    add_job(required=["Python"])
    job_id = start_match(env)
    log = messages(job_id)
    assert log and not [line for line in log if any(word in line for word in PRIVATE)]


# --- Adjustable weights (LLD §7.4) -------------------------------------------------------------------


def weights_info(env) -> dict:
    response = env["api"].get("/matching/weights")
    assert response.status_code == 200, response.text
    return response.json()


def test_weights_endpoint_before_any_run(env):
    assert weights_info(env) == {
        "default": DEFAULT_WEIGHTS,
        "active": {"weights": DEFAULT_WEIGHTS, "source": "default", "background_job_id": None},
        "results": None,
    }


def test_run_without_weights_records_and_uses_the_default(env):
    worked_example()
    job_id = start_match(env)
    assert job_row(job_id).params == {"weights": DEFAULT_WEIGHTS}
    assert "Weights: required 70, nice-to-have 15, experience 10, location 5." in messages(job_id)
    assert next(iter(stored().values())).score == 71.66666666666667  # the baseline worked example, unchanged


def test_custom_weights_change_the_scores_exactly(env):
    person, worked = worked_example()  # R = 3/4, N = 1/2, E = 2/3, L = 1
    only_required = start_match(env, {"required": 100, "nice": 0, "experience": 0, "location": 0})
    pair = stored()[(person, worked)]
    assert pair.score == 75.0
    assert pair.explanation == ("Score 75.00/100. Has 3 of 4 required skills (75.00 pts; missing Docker). Has 1 of 2 "
                                "nice-to-have skills (0.00 pts; missing Kubernetes). 2 years of experience against a "
                                "3-year minimum (0.00 pts). Same city, Pune (0.00 pts).")
    assert pair.matched_skills[0] == {"skill": "FastAPI", "level": "required"}  # skills are unaffected by weights
    assert "Weights: required 100, nice-to-have 0, experience 0, location 0." in messages(only_required)

    start_match(env, {"required": 25, "nice": 25, "experience": 25, "location": 25})
    pair = stored()[(person, worked)]
    assert pair.score == 875 / 12  # 18.75 + 12.5 + 16.67 + 25, exact before it is stored
    assert [pair.score_breakdown[part]["points"] for part in ("required", "nice_to_have", "experience", "location")] == [
        18.75, 12.5, 25 * 2 / 3, 25.0]
    item = env["api"].get(f"/candidates/{person}/matches").json()["items"][0]
    assert item["score"] == 72.92 and item["explanation"].startswith("Score 72.92/100.")


def test_edge_case_rules_hold_with_custom_weights(env):
    person = add_candidate(skills=["Python", "Docker"], years=5, city="Bengaluru")
    empty = add_job(location="Bengaluru")                                  # no skills at all: R = N = 0
    no_nice = add_job(required=["Python", "Docker"], location="Mumbai")    # no nice-to-have list: N = 1
    only_nice = add_job(nice=["Docker", "AWS"], location="Bangalore")      # no required skills: R = 0
    start_match(env, {"required": 25, "nice": 25, "experience": 25, "location": 25})
    matches = stored()
    assert matches[(person, empty)].score == 0 + 0 + 25 + 25
    assert matches[(person, no_nice)].score == 25 + 25 + 25 + 0
    assert matches[(person, only_nice)].score == 0 + 12.5 + 25 + 25
    assert matches[(person, no_nice)].score_breakdown["nice_to_have"]["rule"] == "none_listed"


def test_runs_without_weights_keep_the_active_weights(env):
    worked_example()
    custom = {"required": 50, "nice": 20, "experience": 20, "location": 10}
    chosen = start_match(env, custom)
    later = start_match(env)  # no weights: the active ones
    assert job_row(later).params == {"weights": custom}
    info = weights_info(env)
    assert info["active"] == {"weights": custom, "source": "match_run", "background_job_id": str(later)}
    assert info["results"] == {"background_job_id": str(later), "weights": custom}
    assert info["default"] == DEFAULT_WEIGHTS  # the default never changes
    assert job_row(chosen).status == "completed"


def test_failed_and_cancelled_runs_do_not_change_the_active_weights(env, monkeypatch):
    worked_example()
    kept = {"required": 50, "nice": 20, "experience": 20, "location": 10}
    good = start_match(env, kept)

    real = tasks.score_candidate
    monkeypatch.setattr(tasks, "score_candidate", lambda *args: (_ for _ in ()).throw(RuntimeError("boom")))
    failed = start_match(env, {"required": 90, "nice": 5, "experience": 5, "location": 0})
    monkeypatch.setattr(tasks, "score_candidate", real)
    assert job_row(failed).status == "failed"

    env["run_later"] = True
    cancelled = start_match(env, {"required": 80, "nice": 10, "experience": 5, "location": 5})
    assert env["api"].post(f"/background-jobs/{cancelled}/cancel").json() == {"status": "cancelled"}

    info = weights_info(env)
    assert info["active"] == {"weights": kept, "source": "match_run", "background_job_id": str(good)}
    assert info["results"] == {"background_job_id": str(good), "weights": kept}
    assert job_row(start_match(env)).params == {"weights": kept}  # a queued run without weights inherits them

    # A queued run is the latest choice: it becomes active at once, before it has any results.
    queued = start_match(env, {"required": 60, "nice": 20, "experience": 10, "location": 10})
    info = weights_info(env)
    assert info["active"]["background_job_id"] == str(queued)
    assert info["active"]["weights"] == {"required": 60, "nice": 20, "experience": 10, "location": 10}
    assert info["results"]["background_job_id"] == str(good)  # the stored results are still the good run's


def test_runs_from_before_weights_were_recorded(env):
    worked_example()
    with SessionLocal() as session:  # a completed run from before this feature: params = None
        old = BackgroundJob(type="match", status="completed", params=None, started_at=func.now(), finished_at=func.now())
        queued_before = BackgroundJob(type="match", status="queued", params=None)  # queued before the deployment
        session.add_all([old, queued_before])
        session.commit()
        old_id, queued_id = old.background_job_id, queued_before.background_job_id

    info = weights_info(env)
    assert info["results"] == {"background_job_id": str(old_id), "weights": None}  # shown as "not recorded"
    assert info["active"] == {"weights": DEFAULT_WEIGHTS, "source": "default", "background_job_id": None}
    detail = env["api"].get(f"/background-jobs/{old_id}").json()
    assert detail["params"] is None  # unchanged: old runs keep params = null

    assert run_task(queued_id) == "completed"  # the worker falls back to MATCH_WEIGHTS, as before
    assert ("Weights: required 70, nice-to-have 15, experience 10, location 5 (MATCH_WEIGHTS; this run has no "
            "recorded weights).") in messages(queued_id)
    assert next(iter(stored().values())).score == 71.66666666666667


def test_invalid_weights_create_no_job(env):
    worked_example()
    response = env["api"].post("/background-jobs/match", json={"weights": {**DEFAULT_WEIGHTS, "location": 4}})
    assert response.status_code == 422
    with SessionLocal() as session:
        assert session.execute(select(func.count()).select_from(BackgroundJob)).scalar_one() == 0


# --- The two match routes ---------------------------------------------------------------------------


def test_candidate_matches_route(env):
    person, worked = worked_example()
    for n in range(11):  # 12 jobs in all, so the limit of 10 matters
        add_job(required=["Python"] + (["Rust"] * (n % 2)), minimum=n % 4, location="Mumbai", title=f"Job {n}")
    start_match(env)

    body = env["api"].get(f"/candidates/{person}/matches").json()
    assert body["candidate_id"] == str(person)
    assert body["computed_at"] is not None
    items = body["items"]
    assert [item["rank"] for item in items] == list(range(1, 11))
    assert [item["score"] for item in items] == sorted((item["score"] for item in items), reverse=True)

    top = next(item for item in items if item["job_id"] == str(worked))
    assert top == {
        "rank": top["rank"], "job_id": str(worked), "title": "Backend Python Developer", "company": "Acme Analytics",
        "score": 71.67,
        "matched_skills": [{"skill": "FastAPI", "level": "required"}, {"skill": "PostgreSQL", "level": "required"},
                           {"skill": "Python", "level": "required"}, {"skill": "Redis", "level": "nice_to_have"}],
        "missing_skills": [{"skill": "Docker", "level": "required"}, {"skill": "Kubernetes", "level": "nice_to_have"}],
        "breakdown": {
            "required": {"matched": 3, "total": 4, "ratio": 0.75, "points": 52.5, "rule": "ratio"},
            "nice_to_have": {"matched": 1, "total": 2, "ratio": 0.5, "points": 7.5, "rule": "ratio"},
            "experience": {"candidate_years": 2.0, "minimum": 3.0, "fit": 0.667, "points": 6.67, "rule": "ratio"},
            "location": {"candidate_city": "Pune", "job_location": "Pune, India", "job_city": "Pune", "fit": 1.0,
                         "points": 5.0, "rule": "same_city"},
        },
        "text_similarity": 0.0,
        "explanation": WORKED_SENTENCE,
    }
    assert len(env["api"].get(f"/candidates/{person}/matches", params={"limit": 3}).json()["items"]) == 3


def test_job_matches_route(env):
    job = add_job(required=["Python", "Docker"], nice=["AWS"], minimum=2, location="Bangalore")
    people = [add_candidate(skills=["Python", "Docker", "AWS"][: n % 4], years=n % 5, city="Bengaluru" if n % 2 else "Pune",
                            name=f"Person {n}", title=f"Title {n}") for n in range(12)]
    start_match(env)

    body = env["api"].get(f"/jobs/{job}/matches").json()
    assert body["job_id"] == str(job)
    items = body["items"]
    assert len(items) == 10 and [item["rank"] for item in items] == list(range(1, 11))
    first = items[0]
    assert set(first) == {"rank", "candidate_id", "name", "current_title", "city", "score", "matched_skills",
                          "missing_skills", "breakdown", "text_similarity", "explanation"}
    assert uuid.UUID(first["candidate_id"]) in people
    assert first["name"].startswith("Person ") and first["city"] in {"Pune", "Bengaluru"}
    assert first["score"] == 100.0  # all three skills, 3+ years, Bengaluru = Bangalore


@pytest.mark.parametrize("path", ["/candidates/{id}/matches", "/jobs/{id}/matches"])
def test_unknown_ids_give_404(env, path):
    response = env["api"].get(path.format(id=uuid.uuid4()))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_api_order_equals_the_ranking_rule_for_every_candidate_and_job(env):
    """Many exact ties: the SQL order (score, similarity, required ratio, ID) must equal rank_key."""
    rng = random.Random(7)
    vocabulary = ["Python", "Java", "Docker", "AWS", "SQL", "React"]
    words = ["python", "java", "docker", "cloud", "sql", "react", "api", "data"]
    jobs = [add_job(required=rng.sample(vocabulary, rng.randint(0, 2)), nice=[], minimum=rng.choice([None, 1, 3]),
                    location=rng.choice(["Pune", "Mumbai", None]), remote=rng.random() < 0.2,
                    description=" ".join(rng.choices(words, k=6))) for _ in range(14)]
    people = [add_candidate(skills=rng.sample(vocabulary, rng.randint(0, 3)), years=rng.choice([None, 0, 2, 5]),
                            city=rng.choice(["Pune", "Mumbai", None]), resume=" ".join(rng.choices(words, k=8)))
              for _ in range(12)]
    start_match(env)
    matches = stored()

    def expected(pairs, other):
        return [str(getattr(m, other)) for m in sorted(pairs, key=lambda m: rank_key(
            m.score, m.text_similarity, m.score_breakdown["required"]["ratio"], getattr(m, other)))][:10]

    for person in people:
        api = [item["job_id"] for item in env["api"].get(f"/candidates/{person}/matches").json()["items"]]
        assert api == expected([m for (c, _), m in matches.items() if c == person], "job_id")
    for job in jobs:
        api = [item["candidate_id"] for item in env["api"].get(f"/jobs/{job}/matches").json()["items"]]
        assert api == expected([m for (_, j), m in matches.items() if j == job], "candidate_id")


# --- Score precision through the database and the API (LLD §9.7) ------------------------------------


def _breakdown(ratio: float = 1.0) -> dict:
    skills = {"matched": 1, "total": 1, "ratio": ratio, "points": 70 * ratio, "rule": "ratio"}
    return {"required": skills, "nice_to_have": {**skills, "ratio": 1.0, "points": 15.0},
            "experience": {"candidate_years": None, "minimum": None, "fit": 1.0, "points": 10.0, "rule": "no_minimum"},
            "location": {"candidate_city": None, "job_location": None, "job_city": None, "fit": 0.0, "points": 0.0,
                         "rule": "candidate_city_unknown"}}


def _insert_matches(person: uuid.UUID, rows: list[tuple[uuid.UUID, float, float, float]]) -> None:
    with SessionLocal() as session:
        session.add_all([Match(candidate_id=person, job_id=job, score=score, text_similarity=similarity,
                               score_breakdown=_breakdown(ratio), matched_skills=[], missing_skills=[],
                               explanation=f"Score {score:.2f}/100.") for job, score, similarity, ratio in rows])
        session.commit()


def _api_order(env, person) -> list[dict]:
    return env["api"].get(f"/candidates/{person}/matches").json()["items"]


def test_precision_1_scores_that_display_the_same_keep_their_order(env):
    person = add_candidate()
    a, b = add_job(), add_job()
    _insert_matches(person, [(a, 80.001, 0.9, 1.0), (b, 80.004, 0.1, 1.0)])
    items = _api_order(env, person)
    assert [item["job_id"] for item in items] == [str(b), str(a)]  # 80.004 first despite lower similarity
    assert [item["score"] for item in items] == [80.0, 80.0]


def test_precision_2_top_10_boundary(env):
    person = add_candidate()
    jobs = [add_job() for _ in range(11)]
    rows = [(jobs[n], 90.0 - n, 0.5, 1.0) for n in range(9)]
    rows += [(jobs[9], 50.001, 0.99, 1.0), (jobs[10], 50.004, 0.01, 1.0)]
    _insert_matches(person, rows)
    ids = [item["job_id"] for item in _api_order(env, person)]
    assert len(ids) == 10 and str(jobs[10]) in ids and str(jobs[9]) not in ids


def test_precision_3_equal_scores_go_to_the_tie_breakers(env):
    person = add_candidate()
    jobs = sorted(add_job() for _ in range(4))
    exact = float(Decimal(215) / Decimal(3))  # 71 2/3 stored identically, whatever produced it
    _insert_matches(person, [(jobs[3], exact, 0.2, 1.0),   # tie on similarity with jobs[2] -> ratio decides
                             (jobs[2], exact, 0.2, 0.5),
                             (jobs[1], exact, 0.6, 0.0),   # highest similarity first
                             (jobs[0], exact, 0.2, 0.5)])  # same as jobs[2]: lower ID first
    assert [item["job_id"] for item in _api_order(env, person)] == [str(j) for j in (jobs[1], jobs[3], jobs[0], jobs[2])]


def test_precision_4_stored_versus_shown(env):
    person, worked = worked_example()
    start_match(env)
    with SessionLocal() as session:
        raw = session.execute(text("SELECT score FROM matches")).scalar_one()
    item = _api_order(env, person)[0]
    assert raw == 71.66666666666667
    assert item["score"] == 71.67 and item["rank"] == 1
    assert item["explanation"].startswith("Score 71.67/100.")
    assert item["breakdown"]["experience"]["points"] == 6.67
