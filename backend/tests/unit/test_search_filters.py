"""The search filter builders, compiled to SQL without a database (LLD §4.4, HLD §9.4). Offline.

The behaviour against real rows is tested in tests/integration/test_search_api.py.
"""

from decimal import Decimal

from sqlalchemy.dialects import postgresql

from app.locations.normalizer import spellings_of
from app.schemas.candidate import CandidateSearchParams
from app.schemas.job import JobSearchParams
from app.services import search


def sql(statement) -> str:
    """The statement as PostgreSQL text with literal values ("%" is doubled by psycopg's parameter style)."""
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_like_wildcards_in_user_input_are_literal():
    assert search.escape_like("50%_off\\") == "50\\%\\_off\\\\"
    assert sql(search.contains(search.Job.title, "100%_x")) == "jobs.title ILIKE '%%100\\%%\\_x%%' ESCAPE '\\'"


def test_skill_terms_are_normalized():
    assert search.canonical_skill("js") == "JavaScript"
    assert search.canonical_skill("ReactJS") == "React"
    assert search.canonical_skill(" postgres ") == "PostgreSQL"
    assert search.canonical_skill("cobol") is None


def where(statement) -> str:
    text = sql(statement)
    return text[text.rfind("WHERE"):]


def test_unknown_skill_matches_nothing():
    assert where(search.jobs_statement(JobSearchParams(skill="cobol", location="pune"))).startswith("WHERE false ORDER")


def test_known_city_matches_all_its_spellings():
    assert spellings_of("Bengaluru") == ("Bengaluru", "Bangalore")
    assert search.city_names("bangalore, karnataka") == ("Bengaluru", "Bangalore")
    assert search.city_names("Stewartbury") is None
    assert where(search.jobs_statement(JobSearchParams(location="Bangalore"))).startswith(
        "WHERE jobs.location ILIKE '%%Bengaluru%%' ESCAPE '\\' OR jobs.location ILIKE '%%Bangalore%%' ESCAPE '\\' ORDER")
    assert where(search.jobs_statement(JobSearchParams(location="Stewartbury"))).startswith(
        "WHERE jobs.location ILIKE '%%Stewartbury%%' ESCAPE '\\' ORDER")
    assert where(search.candidates_statement(CandidateSearchParams(city="bangalore"))).startswith(
        "WHERE candidates.city IN ('Bengaluru', 'Bangalore') ORDER")
    assert where(search.candidates_statement(CandidateSearchParams(city="Stewartbury"))).startswith(
        "WHERE lower(candidates.city) = 'stewartbury' ORDER")


def test_experience_filter_keeps_jobs_without_a_minimum():
    text = sql(search.jobs_statement(JobSearchParams(max_required_years=Decimal(3))))
    assert "jobs.min_experience_years IS NULL OR jobs.min_experience_years <= 3" in text


def test_sorting_puts_missing_values_last_and_breaks_ties_by_id():
    newest = sql(search.jobs_statement(JobSearchParams()))
    assert "ORDER BY jobs.posted_date DESC NULLS LAST, jobs.job_id ASC" in newest
    oldest = sql(search.jobs_statement(JobSearchParams(order="asc")))
    assert "ORDER BY jobs.posted_date ASC NULLS LAST, jobs.job_id ASC" in oldest
    titles = sql(search.jobs_statement(JobSearchParams(sort="title")))
    assert "ORDER BY lower(jobs.title) ASC NULLS LAST, jobs.job_id ASC" in titles
    people = sql(search.candidates_statement(CandidateSearchParams(sort="years_experience")))
    assert "ORDER BY candidates.years_experience DESC NULLS LAST, candidates.candidate_id ASC" in people


def test_candidate_queries_never_select_internal_columns():
    for statement in (search.candidates_statement(CandidateSearchParams()),
                      search.select(*search.CANDIDATE_DETAIL_COLUMNS)):
        text = sql(statement)
        for column in ("stored_path", "resume_text", "file_sha256", "background_job_id"):
            assert column not in text


def test_skills_come_with_the_row():
    """Skills are aggregated inside the row's query: no extra query per job or candidate."""
    text = sql(search.jobs_statement(JobSearchParams()))
    assert text.count("array_agg(") == 2 and "required_skills" in text and "nice_to_have_skills" in text


def test_numbers():
    assert search.number(Decimal("3")) == 3 and isinstance(search.number(Decimal("3.0")), int)
    assert search.number(Decimal("2.5")) == 2.5
    assert search.number(None) is None
