"""Saving crawled jobs: upsert by dedup_key, merging, skill links and the taxonomy sync (LLD §3.6, §5.17)."""

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.crawler.pipeline import build_record, save_records
from app.extractors.base import RawJob
from app.extractors.registry import get_registry
from app.models import BackgroundJob, Job, JobSkill, Skill
from app.skills.normalizer import get_taxonomy
from app.skills.sync import skill_ids, sync_skills
from tests.crawl_fakes import fixture

FETCHED_AT = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
APPLY = "https://careers.example.com/jobs/backend-python-developer"
LISTING = "http://mock-site:8080/static/index.html"
DETAIL = "http://mock-site:8080/static/jobs/backend-python-developer.html"


def built(page_url=LISTING, **fields):
    raw = RawJob(**{"title": "Backend Python Developer", "company": "Acme Analytics", "location": "Pune, India",
                    "apply_url": APPLY, **fields})
    return build_record(raw, page_url=page_url, source="mock_static", fetched_at=FETCHED_AT)


def skills_of(session, job_id) -> dict[str, str]:
    rows = session.execute(select(Skill.canonical_name, JobSkill.requirement_level).join(Skill)
                           .where(JobSkill.job_id == job_id)).all()
    return dict(rows)


def test_skills_table_is_synchronized_from_the_taxonomy(session):
    assert sync_skills(session) == len(get_taxonomy().canonical_names)
    sync_skills(session)  # again: no duplicates
    count = session.execute(select(func.count()).select_from(Skill)).scalar_one()
    assert count == len(get_taxonomy().canonical_names)
    assert session.execute(select(Skill.category).where(Skill.canonical_name == "PostgreSQL")).scalar_one() == "database"


def test_skill_ids_inserts_missing_names(session):
    ids = skill_ids(session, {"Python", "Docker"})
    assert set(ids) == {"Python", "Docker"} and len(set(ids.values())) == 2
    assert skill_ids(session, ["Python"]) == {"Python": ids["Python"]}


def test_listing_and_detail_pages_merge_into_one_job(session):
    crawl = BackgroundJob(type="crawl", status="running")
    session.add(crawl)
    session.flush()

    first = save_records(session, [built(job_type="Full-time", salary_text="₹9,00,000 – ₹14,00,000 per year")],
                         crawl.background_job_id)
    second = save_records(session, [built(page_url=DETAIL, description=(
        "Requirements\n- 3+ years of experience with Python\n- PostgreSQL\n- Docker is a plus\nNice to have\n- Redis"),
        posted_date="2026-11-03")], crawl.background_job_id)
    assert (first.inserted, first.updated, second.inserted, second.updated) == (1, 0, 0, 1)

    job = session.execute(select(Job)).scalar_one()  # one row, not two
    assert job.dedup_key == APPLY and job.source_url == DETAIL
    assert (job.job_type, job.salary_min, job.salary_currency) == ("full_time", 900000, "INR")  # kept from the listing
    assert job.description.startswith("Requirements") and str(job.min_experience_years) == "3"
    assert job.background_job_id == crawl.background_job_id
    assert skills_of(session, job.job_id) == {"Python": "required", "PostgreSQL": "required",
                                              "Docker": "nice_to_have", "Redis": "nice_to_have"}


def test_a_later_listing_card_does_not_erase_known_values(session):
    save_records(session, [built(page_url=DETAIL, job_type="Contract", location="Remote",
                                 description="Requirements: Python, Docker")], None)
    save_records(session, [built(job_type=None, company=None)], None)  # listing again: less information
    job = session.execute(select(Job)).scalar_one()
    assert job.job_type == "contract"          # 'unknown' never overwrites a known type
    assert job.company == "Acme Analytics"     # an empty value never erases a known one
    assert job.location == "Pune, India"       # the newer non-empty value wins...
    assert job.is_remote                       # ...but remote stays true once seen
    assert job.description == "Requirements: Python, Docker"
    assert skills_of(session, job.job_id) == {"Python": "required", "Docker": "required"}


def test_new_skill_information_replaces_the_old_links(session):
    save_records(session, [built(description="Requirements: Python, Docker")], None)
    save_records(session, [built(description="Requirements: Go\nNice to have: Docker")], None)
    job = session.execute(select(Job)).scalar_one()
    assert skills_of(session, job.job_id) == {"Go": "required", "Docker": "nice_to_have"}


FAKE_JOBS = "https://realpython.github.io/fake-jobs/"


def test_a_listing_only_job_gets_its_description_and_skills_from_a_later_crawl(session):
    """Production, 24 November 2026: a crawl cut off by max_pages saved Fake Python Jobs from the listing
    page only, with no description and so no skills. A later crawl that reaches their detail pages fills
    them in, in place, with the source's own location; a posting whose text names no technology still
    gets no skills (nothing is invented)."""
    extractor = get_registry().get("fake_python_jobs")
    first, second = BackgroundJob(type="crawl", status="running"), BackgroundJob(type="crawl", status="running")
    session.add_all([first, second])
    session.flush()

    cards = extractor.parse(FAKE_JOBS, fixture("fake_python_jobs_listing.html")).jobs
    save_records(session, [build_record(card, page_url=FAKE_JOBS, source="fake_python_jobs", fetched_at=FETCHED_AT)
                           for card in cards], first.background_job_id)
    python_url, other_url = FAKE_JOBS + "jobs/senior-python-developer-0.html", FAKE_JOBS + "jobs/manufacturing-systems-engineer-51.html"

    def job(url) -> Job:
        return session.execute(select(Job).where(Job.dedup_key == url)).scalar_one()

    assert job(python_url).description is None and skills_of(session, job(python_url).job_id) == {}

    for url, page in ((python_url, "fake_python_jobs_detail.html"), (other_url, "fake_python_jobs_detail_non_technical.html")):
        detail = extractor.parse(url, fixture(page)).jobs[0]
        result = save_records(session, [build_record(detail, page_url=url, source="fake_python_jobs", fetched_at=FETCHED_AT)],
                              second.background_job_id)
        assert (result.inserted, result.updated) == (0, 1)

    assert session.execute(select(func.count()).select_from(Job)).scalar_one() == 100  # updated in place
    python_job, other = job(python_url), job(other_url)
    assert (python_job.location, other.location) == ("Stewartbury, AA", "Joybury, AE")  # the source's values
    assert python_job.description and other.description.startswith("Improve once worry newspaper laugh benefit.")
    assert skills_of(session, python_job.job_id) == dict.fromkeys(["Agile", "CSS", "Django", "HTML", "Python", "Scrum"], "required")
    assert skills_of(session, other.job_id) == {}


def test_different_jobs_stay_separate(session):
    result = save_records(session, [built(), built(apply_url="https://careers.example.com/jobs/other", title="Other")], None)
    assert result.inserted == 2
    assert session.execute(select(func.count()).select_from(Job)).scalar_one() == 2
