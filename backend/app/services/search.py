"""Job and candidate search, detail reads and the skill list (LLD §4.2-4.6, HLD §9.4).

One filter builder per entity serves the search, the detail read and the exports, so an export
contains exactly what the search shows ("what you see is what you export").

- **Text search** (`q`): case-insensitive substring over the columns with trigram indexes:
  job title and company; candidate name and current title. `%`, `_` and `\\` in the input are
  matched literally.
- **Skill filter**: the term goes through the taxonomy normalizer first ("js" -> JavaScript), then
  an EXISTS on the link table (index on skill_id). A term that is not a known skill matches nothing.
- **Location / city**: a known city also matches its other spellings ("Bangalore" = "Bengaluru").
- **Sorting** (decision LLD-5): only allow-listed fields; missing values last in both directions;
  equal values ordered by ID, so pages never repeat or skip a row.
- **Skills of each row** are collected inside the same query (a correlated `array_agg`), so a page
  costs two queries (count + page) and a detail read one, whatever the number of rows or skills.

Internal candidate columns (`stored_path`, `resume_text`, `file_sha256`, `background_job_id`) are
never selected here.
"""

import uuid
from decimal import Decimal

from sqlalchemy import ColumnElement, Select, exists, false, func, or_, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import Session

from app.errors import AppError
from app.locations.normalizer import normalize_city, spellings_of
from app.models import Candidate, CandidateSkill, Job, JobSkill, Skill
from app.schemas.candidate import CandidateDetail, CandidateFilterParams, CandidateList, CandidateSearchParams, \
    CandidateSummary, EducationEntry
from app.schemas.job import JobDetail, JobFilterParams, JobList, JobSearchParams, JobSummary, Salary
from app.schemas.skill import SkillItem, SkillList
from app.skills.normalizer import get_taxonomy

DEFAULT_ORDER = {"posted_date": "desc", "title": "asc", "name": "asc", "years_experience": "desc"}


# --- Building blocks -----------------------------------------------------------------------------


def escape_like(text: str) -> str:
    """Make LIKE wildcards in user input literal (used with ESCAPE '\\')."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def contains(column, text: str) -> ColumnElement[bool]:
    """Case-insensitive substring match; PostgreSQL can use a trigram index for it."""
    return column.ilike(f"%{escape_like(text)}%", escape="\\")


def canonical_skill(term: str) -> str | None:
    """The canonical skill name of a filter term ("js" -> "JavaScript"), or None if it is not a skill."""
    return get_taxonomy().canonical(term)


def city_names(text: str) -> tuple[str, ...] | None:
    """All spellings of a known city in the text, or None for an unknown city."""
    canonical = normalize_city(text)
    return spellings_of(canonical) if canonical else None


def number(value: Decimal | None) -> int | float | None:
    """A numeric column as a JSON number: 3 rather than "3" or 3.0; 2.5 stays 2.5."""
    if value is None:
        return None
    return int(value) if value == value.to_integral_value() else float(value)


def _names(rows) -> list[str]:
    return list(rows or [])


def _ordering(column, order: str, *, case_insensitive: bool = False) -> ColumnElement:
    key = func.lower(column) if case_insensitive else column
    return (key.asc() if order == "asc" else key.desc()).nulls_last()


# --- Jobs ------------------------------------------------------------------------------------------


def _job_skill_names(level: str):
    """The job's skills of one level, alphabetical, as one array value (NULL when there are none)."""
    name = Skill.canonical_name
    return (select(func.array_agg(aggregate_order_by(name, func.lower(name), name)))
            .join(JobSkill, JobSkill.skill_id == Skill.skill_id)
            .where(JobSkill.job_id == Job.job_id, JobSkill.requirement_level == level)
            .scalar_subquery())


JOB_SUMMARY_COLUMNS = (
    Job.job_id, Job.title, Job.company, Job.location, Job.job_type, Job.salary_min, Job.salary_max,
    Job.salary_currency, Job.salary_period, Job.posted_date, Job.min_experience_years, Job.apply_url, Job.source,
    _job_skill_names("required").label("required_skills"),
    _job_skill_names("nice_to_have").label("nice_to_have_skills"),
)
JOB_DETAIL_COLUMNS = JOB_SUMMARY_COLUMNS + (
    Job.is_remote, Job.description, Job.salary_text, Job.source_url, Job.created_at, Job.updated_at,
)


def job_conditions(params: JobFilterParams) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if params.q:
        conditions.append(or_(contains(Job.title, params.q), contains(Job.company, params.q)))
    if params.skill:
        name = canonical_skill(params.skill)
        if name is None:
            conditions.append(false())  # no job can have a skill that is not in the taxonomy
        else:
            conditions.append(exists(
                select(JobSkill.job_id).join(Skill, Skill.skill_id == JobSkill.skill_id)
                .where(JobSkill.job_id == Job.job_id, Skill.canonical_name == name)))
    if params.location:
        spellings = city_names(params.location) or (params.location,)
        conditions.append(or_(*(contains(Job.location, spelling) for spelling in spellings)))
    if params.job_type:
        conditions.append(Job.job_type == params.job_type)
    if params.max_required_years is not None:
        # "Which jobs suit someone with N years": jobs without a minimum count too (decision LLD-6).
        conditions.append(or_(Job.min_experience_years.is_(None), Job.min_experience_years <= params.max_required_years))
    return conditions


def job_order(params: JobFilterParams) -> tuple[ColumnElement, ...]:
    order = params.order or DEFAULT_ORDER[params.sort]
    key = (_ordering(Job.posted_date, order) if params.sort == "posted_date"
           else _ordering(Job.title, order, case_insensitive=True))
    return key, Job.job_id.asc()


def jobs_statement(params: JobFilterParams, *, detail: bool = False) -> Select:
    """The filtered, ordered job query, without paging (the export streams all of it)."""
    columns = JOB_DETAIL_COLUMNS if detail else JOB_SUMMARY_COLUMNS
    return select(*columns).where(*job_conditions(params)).order_by(*job_order(params))


def _salary(row) -> Salary | None:
    values = (row.salary_min, row.salary_max, row.salary_currency, row.salary_period)
    if all(value is None for value in values):
        return None
    return Salary(min=number(row.salary_min), max=number(row.salary_max), currency=row.salary_currency,
                  period=row.salary_period)


def job_summary(row) -> JobSummary:
    return JobSummary(
        job_id=row.job_id, title=row.title, company=row.company, location=row.location, job_type=row.job_type,
        salary=_salary(row), posted_date=row.posted_date, required_skills=_names(row.required_skills),
        nice_to_have_skills=_names(row.nice_to_have_skills), min_experience_years=number(row.min_experience_years),
        apply_url=row.apply_url, source=row.source,
    )


def job_detail(row) -> JobDetail:
    return JobDetail(
        **job_summary(row).model_dump(), is_remote=row.is_remote, description=row.description,
        salary_text=row.salary_text, source_url=row.source_url, created_at=row.created_at, updated_at=row.updated_at,
    )


def search_jobs(session: Session, params: JobSearchParams) -> JobList:
    """GET /jobs: one page and the total, in two queries."""
    conditions = job_conditions(params)
    total = session.execute(select(func.count()).select_from(Job).where(*conditions)).scalar_one()
    rows = session.execute(jobs_statement(params).offset((params.page - 1) * params.page_size)
                           .limit(params.page_size)).all()
    return JobList(items=[job_summary(row) for row in rows], total=total, page=params.page, page_size=params.page_size)


def get_job(session: Session, job_id: uuid.UUID) -> JobDetail:
    """GET /jobs/{id}: one query, skills included."""
    row = session.execute(select(*JOB_DETAIL_COLUMNS).where(Job.job_id == job_id)).first()
    if row is None:
        raise AppError(404, "NOT_FOUND", "Job not found.")
    return job_detail(row)


# --- Candidates ------------------------------------------------------------------------------------


def _candidate_skill_names():
    name = Skill.canonical_name
    return (select(func.array_agg(aggregate_order_by(name, func.lower(name), name)))
            .join(CandidateSkill, CandidateSkill.skill_id == Skill.skill_id)
            .where(CandidateSkill.candidate_id == Candidate.candidate_id)
            .scalar_subquery())


CANDIDATE_SUMMARY_COLUMNS = (
    Candidate.candidate_id, Candidate.name, Candidate.email, Candidate.phone, Candidate.city, Candidate.current_title,
    Candidate.years_experience, Candidate.education, Candidate.summary, Candidate.source_file,
    Candidate.parsed_with_ocr, _candidate_skill_names().label("skills"),
)
CANDIDATE_DETAIL_COLUMNS = CANDIDATE_SUMMARY_COLUMNS + (
    Candidate.parse_warnings, Candidate.created_at, Candidate.updated_at,
)


def candidate_conditions(params: CandidateFilterParams) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if params.q:
        conditions.append(or_(contains(Candidate.name, params.q), contains(Candidate.current_title, params.q)))
    if params.skill:
        name = canonical_skill(params.skill)
        if name is None:
            conditions.append(false())
        else:
            conditions.append(exists(
                select(CandidateSkill.candidate_id).join(Skill, Skill.skill_id == CandidateSkill.skill_id)
                .where(CandidateSkill.candidate_id == Candidate.candidate_id, Skill.canonical_name == name)))
    if params.city:
        spellings = city_names(params.city)
        if spellings:  # parsed cities are canonical names: an exact match can use the city index
            conditions.append(Candidate.city.in_(spellings))
        else:
            conditions.append(func.lower(Candidate.city) == params.city.lower())
    return conditions


def candidate_order(params: CandidateFilterParams) -> tuple[ColumnElement, ...]:
    order = params.order or DEFAULT_ORDER[params.sort]
    key = (_ordering(Candidate.name, order, case_insensitive=True) if params.sort == "name"
           else _ordering(Candidate.years_experience, order))
    return key, Candidate.candidate_id.asc()


def candidates_statement(params: CandidateFilterParams) -> Select:
    return select(*CANDIDATE_SUMMARY_COLUMNS).where(*candidate_conditions(params)).order_by(*candidate_order(params))


def candidate_summary(row) -> CandidateSummary:
    return CandidateSummary(
        candidate_id=row.candidate_id, name=row.name, email=row.email, phone=row.phone, city=row.city,
        current_title=row.current_title, skills=_names(row.skills), years_experience=number(row.years_experience),
        education=[EducationEntry(**entry) for entry in (row.education or [])], summary=row.summary,
        source_file=row.source_file, parsed_with_ocr=row.parsed_with_ocr,
    )


def search_candidates(session: Session, params: CandidateSearchParams) -> CandidateList:
    """GET /candidates: one page and the total, in two queries."""
    conditions = candidate_conditions(params)
    total = session.execute(select(func.count()).select_from(Candidate).where(*conditions)).scalar_one()
    rows = session.execute(candidates_statement(params).offset((params.page - 1) * params.page_size)
                           .limit(params.page_size)).all()
    return CandidateList(items=[candidate_summary(row) for row in rows], total=total, page=params.page,
                         page_size=params.page_size)


def get_candidate(session: Session, candidate_id: uuid.UUID) -> CandidateDetail:
    """GET /candidates/{id}: one query, skills included."""
    row = session.execute(select(*CANDIDATE_DETAIL_COLUMNS).where(Candidate.candidate_id == candidate_id)).first()
    if row is None:
        raise AppError(404, "NOT_FOUND", "Candidate not found.")
    return CandidateDetail(**candidate_summary(row).model_dump(), parse_warnings=list(row.parse_warnings or []),
                           created_at=row.created_at, updated_at=row.updated_at)


# --- Skills ----------------------------------------------------------------------------------------


def list_skills(session: Session) -> SkillList:
    """GET /skills: every canonical skill on one page, by name (decision LLD-2)."""
    rows = session.execute(select(Skill.canonical_name, Skill.category)
                           .order_by(func.lower(Skill.canonical_name), Skill.canonical_name)).all()
    items = [SkillItem(skill=row.canonical_name, category=row.category) for row in rows]
    return SkillList(items=items, total=len(items), page=1, page_size=len(items))
