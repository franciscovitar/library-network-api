"""Alembic migrations against a real PostgreSQL server."""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from alembic import command
from app.persistence.models import Base
from tests.integration.conftest import alembic_config

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {
    "branches",
    "members",
    "books",
    "copies",
    "loans",
    "transfers",
    "transfer_events",
    "idempotency_records",
}


def test_upgrade_head_creates_schema_and_records_revision(engine, migrated_url):
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
    head = ScriptDirectory.from_config(alembic_config(migrated_url)).get_current_head()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == head


def test_migrated_schema_has_no_drift_from_models(engine):
    """The reviewed migration and the SQLAlchemy models describe the same schema."""
    with engine.connect() as conn:
        context = MigrationContext.configure(
            conn, opts={"compare_type": True, "compare_server_default": True}
        )
        assert compare_metadata(context, Base.metadata) == []


def test_nonterminal_loan_index_is_unique_and_partial(engine):
    with engine.connect() as conn:
        definition = conn.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_loans_copy_id_nonterminal'")
        ).scalar_one()
    assert "UNIQUE" in definition
    assert "(copy_id)" in definition
    for state in ("REQUESTED", "ACTIVE", "RETURNING"):
        assert state in definition
    assert "CLOSED" not in definition


def test_idempotency_fk_is_deferrable_initially_deferred(engine):
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT condeferrable, condeferred FROM pg_constraint "
                "WHERE conname = 'fk_idempotency_records_resource_id_loans'"
            )
        ).one()
    assert tuple(row) == (True, True)


def test_downgrade_to_base_and_upgrade_again(engine, migrated_url):
    """Round trip on a disposable database (downgrade is destructive by nature)."""
    cfg = alembic_config(migrated_url)
    command.downgrade(cfg, "base")
    assert not (EXPECTED_TABLES & set(inspect(engine).get_table_names()))
    command.upgrade(cfg, "head")
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
