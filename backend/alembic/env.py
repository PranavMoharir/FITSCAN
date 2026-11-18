"""Alembic migration environment.

The database URL comes from DATABASE_URL (via app.config), never from alembic.ini.
`target_metadata` is the metadata of all SQLAlchemy models, so
`alembic revision --autogenerate -m "..."` can compare the models with the database.

The API container runs `alembic upgrade head` before it starts serving (HLD §16.1).
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

import app.models  # noqa: F401  (imports every model, so all tables are registered on Base.metadata)
from app.config import get_settings
from app.db.base import Base
from app.db.session import CONNECT_TIMEOUT_SECONDS

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
database_url = get_settings().database_url


def run_migrations_offline() -> None:
    """Write the migration SQL to stdout instead of running it (alembic upgrade head --sql)."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and run the migrations."""
    connectable = create_engine(
        database_url,
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},  # fail instead of hanging
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
