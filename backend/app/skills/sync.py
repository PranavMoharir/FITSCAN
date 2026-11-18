"""Keep the `skills` table in step with taxonomy.json (LLD §3.3, §6.8).

`sync_skills` runs when the worker starts. `skill_ids` is used when job skills are saved; it
also inserts any missing name, so saving never depends on the start-up order.
Skills that disappear from the taxonomy are not deleted, because job and candidate links may
still point to them.
"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Skill
from app.skills.normalizer import get_taxonomy


def sync_skills(session: Session) -> int:
    """Insert or update every canonical skill of the taxonomy. Returns the number of skills."""
    taxonomy = get_taxonomy()
    rows = [{"canonical_name": name, "category": taxonomy.categories[name]} for name in taxonomy.canonical_names]
    statement = insert(Skill).values(rows)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[Skill.canonical_name], set_={"category": statement.excluded.category}
        )
    )
    return len(rows)


def skill_ids(session: Session, names: set[str] | list[str]) -> dict[str, int]:
    """skill_id for each canonical name, inserting names that are not in the table yet."""
    names = sorted(set(names))
    if not names:
        return {}
    taxonomy = get_taxonomy()
    session.execute(
        insert(Skill)
        .values([{"canonical_name": n, "category": taxonomy.categories.get(n)} for n in names])
        .on_conflict_do_nothing(index_elements=[Skill.canonical_name])
    )
    rows = session.execute(select(Skill.canonical_name, Skill.skill_id).where(Skill.canonical_name.in_(names)))
    return {name: skill_id for name, skill_id in rows}
