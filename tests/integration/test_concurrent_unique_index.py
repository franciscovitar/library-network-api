"""Two REAL PostgreSQL connections racing on the nonterminal-loan unique index.

Scope: this proves the *database* second line of defence (partial unique index) under true
concurrency. It does NOT test the application-level copy row lock or idempotency flow, which
belong to the lifecycle/concurrency milestone and are not implemented yet.

Deterministic by construction (no sleeps as synchronisation): connection A inserts without
committing; connection B's insert is observed *blocked on a lock* in pg_stat_activity; only then
does A commit or roll back.
"""

import threading
import time
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

INSERT_LOAN = text(
    "INSERT INTO loans (member_id, copy_id, origin_branch_id, destination_branch_id, status, "
    "requested_at) VALUES (:member, 1, 1, 2, 'REQUESTED', :now)"
)


@pytest.fixture
def seeded_url(migrated_url):
    from sqlalchemy.orm import Session

    from app.persistence.seed import seed_demo_data

    engine = create_engine(migrated_url)
    with Session(engine) as session, session.begin():
        seed_demo_data(session)
    engine.dispose()
    return migrated_url


def _wait_until_blocked(observer, pid: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        wait_type = observer.execute(
            text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"), {"pid": pid}
        ).scalar()
        if wait_type == "Lock":
            return
        time.sleep(0.02)
    raise AssertionError("connection B never blocked on the lock held by connection A")


@pytest.mark.parametrize("a_outcome", ["commit", "rollback"])
def test_concurrent_requests_for_same_copy_have_a_single_winner(seeded_url, a_outcome):
    engine = create_engine(seeded_url)
    now = datetime(2026, 1, 10, tzinfo=UTC)
    result: dict[str, object] = {}
    b_pid: dict[str, int] = {}

    with engine.connect() as conn_a, engine.connect() as observer:
        conn_a.execute(
            INSERT_LOAN, {"member": 1, "now": now}
        )  # A holds the index entry, uncommitted

        def request_b() -> None:
            with engine.connect() as conn_b:
                conn_b.execute(text("SET lock_timeout = '15s'"))  # fail loudly, never hang
                b_pid["pid"] = conn_b.execute(text("SELECT pg_backend_pid()")).scalar_one()
                try:
                    conn_b.execute(INSERT_LOAN, {"member": 2, "now": now})
                    conn_b.commit()
                    result["b"] = "inserted"
                except IntegrityError as exc:
                    conn_b.rollback()
                    result["b"] = exc.orig.diag.constraint_name

        thread = threading.Thread(target=request_b)
        thread.start()
        deadline = time.monotonic() + 10
        while "pid" not in b_pid and time.monotonic() < deadline:
            time.sleep(0.01)
        _wait_until_blocked(observer, b_pid["pid"])  # B is waiting on A's uncommitted row
        assert "b" not in result  # B has not been answered yet

        if a_outcome == "commit":
            conn_a.commit()
        else:
            conn_a.rollback()
        thread.join(timeout=20)
        assert not thread.is_alive()

    with engine.connect() as conn:
        open_loans = conn.execute(
            text("SELECT count(*) FROM loans WHERE copy_id = 1 AND status = 'REQUESTED'")
        ).scalar_one()
    engine.dispose()

    assert open_loans == 1  # never two, whichever connection won
    if a_outcome == "commit":
        assert result["b"] == "uq_loans_copy_id_nonterminal"
    else:
        assert result["b"] == "inserted"
