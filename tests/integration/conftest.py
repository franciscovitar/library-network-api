"""Fixtures for tests that need a REAL PostgreSQL server.

Set TEST_DATABASE_URL to any database URL on a disposable server, e.g. (see compose.test.yaml):

    postgresql+psycopg://library_test:local_test_only@127.0.0.1:55432/postgres

The tests never write to that database itself. Each test module creates its own uniquely named
throwaway database (``lnapi_test_<random>``), builds the schema with ``alembic upgrade head``
(never ``create_all``) and drops ONLY the databases it created. Without TEST_DATABASE_URL the
integration tests are skipped with an explicit reason; they are never replaced by SQLite.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import Session

from alembic import command
from app.persistence.seed import seed_demo_data

ROOT = Path(__file__).resolve().parents[2]
DB_PREFIX = "lnapi_test_"


def alembic_config(url: URL) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    # configparser treats % as interpolation syntax.
    cfg.set_main_option(
        "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
    )
    return cfg


@pytest.fixture(scope="session")
def server_url() -> URL:
    raw = os.getenv("TEST_DATABASE_URL")
    if not raw:
        pytest.skip(
            "TEST_DATABASE_URL not set: real-PostgreSQL integration tests were NOT run "
            "(start compose.test.yaml; see README)."
        )
    return make_url(raw)


@pytest.fixture(scope="session")
def create_database(server_url: URL):
    """Factory returning the URL of a new, uniquely named database (optionally from a template)."""
    created: list[str] = []
    admin = create_engine(server_url, isolation_level="AUTOCOMMIT")

    def _create(template: URL | None = None) -> URL:
        name = f"{DB_PREFIX}{uuid.uuid4().hex[:12]}"
        clause = f' TEMPLATE "{template.database}"' if template is not None else ""
        if template is not None:
            assert template.database.startswith(DB_PREFIX)
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"{clause}'))
        created.append(name)
        return server_url.set(database=name)

    yield _create

    with admin.connect() as conn:
        for name in created:
            assert name.startswith(DB_PREFIX)  # never drop anything we did not create
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def migrated_url(create_database) -> URL:
    """A fresh database upgraded to head by Alembic (no seed)."""
    url = create_database()
    command.upgrade(alembic_config(url), "head")
    return url


@pytest.fixture
def engine(migrated_url: URL) -> Iterator[Engine]:
    eng = create_engine(migrated_url)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def seeded_engine(create_database) -> Iterator[Engine]:
    """Migrated + seeded database shared by a module. Tests must not commit to it."""
    url = create_database()
    command.upgrade(alembic_config(url), "head")
    eng = create_engine(url)
    with Session(eng) as session, session.begin():
        assert seed_demo_data(session) is not None
    yield eng
    eng.dispose()


@pytest.fixture
def db(seeded_engine: Engine) -> Iterator[Session]:
    """Session inside an outer transaction that is ALWAYS rolled back.

    ``session.begin_nested()`` (SAVEPOINT) lets a test provoke a constraint violation and keep
    going; nothing a test does survives it.
    """
    connection = seeded_engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


# --- API-level fixtures (lifecycle, idempotency, rollback, concurrency) ----------------------


@pytest.fixture(scope="session")
def template_url(create_database) -> URL:
    """Migrated + seeded database used as a TEMPLATE: cloning it is much cheaper than
    re-running Alembic for every test, and every clone starts from identical data."""
    url = create_database()
    command.upgrade(alembic_config(url), "head")
    eng = create_engine(url)
    with Session(eng) as session, session.begin():
        assert seed_demo_data(session) is not None
    eng.dispose()  # a template must have no open connections
    return url


@pytest.fixture
def app_engine(create_database, template_url: URL) -> Iterator[Engine]:
    """Engine on a private clone of the seeded database.

    ``lock_timeout`` makes a lock wait that would otherwise hang (a deadlock) fail loudly.
    """
    url = create_database(template=template_url)
    eng = create_engine(
        url,
        pool_size=10,
        max_overflow=10,
        connect_args={"options": "-c lock_timeout=10000 -c statement_timeout=30000"},
    )
    yield eng
    eng.dispose()


class FakeClock:
    """Deterministic, controllable UTC clock (injected through the `get_clock` dependency)."""

    def __init__(self) -> None:
        self.now = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def api(app_engine: Engine, clock: FakeClock) -> Iterator[TestClient]:
    from app.api.routes import get_clock
    from app.db import get_engine
    from app.main import app

    app.dependency_overrides[get_engine] = lambda: app_engine
    app.dependency_overrides[get_clock] = lambda: clock
    yield TestClient(app, raise_server_exceptions=False)  # 500s are asserted, not re-raised
    app.dependency_overrides.clear()
