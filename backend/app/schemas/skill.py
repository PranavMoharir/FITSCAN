"""GET /skills: the canonical skills for filter drop-downs (LLD §4.6, decision LLD-2)."""

from pydantic import BaseModel, ConfigDict, Field


class SkillItem(BaseModel):
    skill: str = Field(description="Canonical name, as used in job and candidate skill lists")
    category: str | None


class SkillList(BaseModel):
    """The standard list shape with every skill on one page, sorted by name. No aliases: the server
    normalizes whatever the user types in a skill filter."""

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "items": [{"skill": "JavaScript", "category": "language"}, {"skill": "PostgreSQL", "category": "database"},
                  {"skill": "React", "category": "framework"}],
        "total": 3, "page": 1, "page_size": 3}]})

    items: list[SkillItem]
    total: int
    page: int = 1
    page_size: int
