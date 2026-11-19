"""/skills: the canonical skills for filter drop-downs (LLD §4.6, decision LLD-2)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.skill import SkillList
from app.services import search

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=SkillList, summary="Canonical skills",
            description="Every skill on one page, sorted by name. The list takes no paging parameters; aliases are "
                        "not listed, because the server normalizes what the user types in a skill filter.")
def list_skills(db: Session = Depends(get_db)) -> SkillList:
    return search.list_skills(db)
