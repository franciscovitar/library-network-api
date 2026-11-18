"""Alembic environment. Online mode only: migrations are reviewed SQL-level changes."""

import os
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from app.persistence.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    url = config.get_main_option("sqlalchemy.url") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL (or sqlalchemy.url) is required to run migrations")
    return url


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline (SQL script) mode is not supported; run against a database.")
run_migrations_online()
