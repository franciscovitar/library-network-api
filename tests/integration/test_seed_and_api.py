"""Synthetic seed and the readiness endpoint against real PostgreSQL."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.db import get_engine
from app.main import app
from app.persistence.models import Book, Branch, Copy, Loan, Member
from app.persistence.seed import seed_demo_data

pytestmark = pytest.mark.integration

EXPECTED_COUNTS = {"branches": 3, "members": 6, "books": 5, "copies": 10}


def counts(session: Session) -> dict[str, int]:
    return {
        name: session.scalar(select(func.count()).select_from(model))
        for name, model in (
            ("branches", Branch),
            ("members", Member),
            ("books", Book),
            ("copies", Copy),
        )
    }


def test_seed_inserts_the_deterministic_dataset(engine):
    with Session(engine) as session, session.begin():
        assert seed_demo_data(session) == EXPECTED_COUNTS
    with Session(engine) as session:
        assert counts(session) == EXPECTED_COUNTS
        copies = session.scalars(select(Copy).order_by(Copy.id)).all()
        assert [c.code for c in copies][:2] == ["CP-0001", "CP-0002"]
        # Every copy starts at its owning branch; only the damaged one is not available.
        assert all(c.current_branch_id == c.owning_branch_id for c in copies)
        assert [c.id for c in copies if c.status != "AVAILABLE"] == [10]
        assert [
            m.code for m in session.scalars(select(Member).where(Member.enabled.is_(False)))
        ] == ["M0006"]
        assert session.scalar(select(func.count()).select_from(Loan)) == 0  # no lifecycle data


def test_seed_is_insert_only_and_refuses_a_non_empty_database(engine):
    with Session(engine) as session, session.begin():
        seed_demo_data(session)
    with Session(engine) as session, session.begin():
        assert seed_demo_data(session) is None  # second run: no-op
    with Session(engine) as session:
        assert counts(session) == EXPECTED_COUNTS


def test_seed_does_not_touch_a_partially_populated_database(engine):
    with Session(engine) as session, session.begin():
        session.add(Branch(name="Someone Else's Branch"))
    with Session(engine) as session, session.begin():
        assert seed_demo_data(session) is None
    with Session(engine) as session:
        assert counts(session) == {"branches": 1, "members": 0, "books": 0, "copies": 0}


def test_sequences_continue_after_the_seeded_ids(engine):
    with Session(engine) as session, session.begin():
        seed_demo_data(session)
    with Session(engine) as session, session.begin():
        branch = Branch(name="Added Later")
        session.add(branch)
        session.flush()
        assert branch.id == 4  # not a collision with seeded ids 1-3


def test_ready_endpoint_succeeds_against_real_postgres(engine):
    app.dependency_overrides[get_engine] = lambda: engine
    try:
        response = TestClient(app).get("/ready")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_endpoint_returns_503_when_postgres_is_unreachable(server_url):
    unreachable = create_engine(
        server_url.set(port=1), connect_args={"connect_timeout": 2}
    )  # nothing listens on port 1
    app.dependency_overrides[get_engine] = lambda: unreachable
    try:
        response = TestClient(app).get("/ready")
    finally:
        app.dependency_overrides.clear()
        unreachable.dispose()
    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}


def test_engine_reports_a_postgres_server(engine):
    with engine.connect() as conn:
        assert "PostgreSQL" in conn.execute(text("SELECT version()")).scalar_one()
