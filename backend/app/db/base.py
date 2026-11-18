"""The declarative base class for all SQLAlchemy models.

Every model in `app/models/` inherits from `Base`, so `Base.metadata` lists all tables.
Alembic compares this metadata with the database to generate migrations.

The naming convention gives every constraint a predictable name (for example
`uq_jobs_dedup_key` or `ck_matches_score_range`), so migrations can refer to them.
"""

from collections.abc import Iterable

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(table_name)s_%(column_0_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def in_values(column: str, values: Iterable[str]) -> str:
    """SQL text for a CHECK constraint that limits a text column to fixed values."""
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"
