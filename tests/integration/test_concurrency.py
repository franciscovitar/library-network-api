"""Concurrent HTTP requests over separate real PostgreSQL connections.

Each worker thread has its own TestClient and therefore its own pooled connection/transaction.
Threads start together behind a barrier. Where noted, a scheduler delay is injected between the
idempotency claim and the copy lock so the interesting interleavings (a request holding its claim
while others arrive) are forced rather than left to chance. The test engine uses
``lock_timeout`` so a deadlock fails the test explicitly instead of hanging it.
"""

import importlib
import itertools
import random
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.application import locks
from app.main import app
from tests.integration.helpers import (
    API,
    activate,
    advance,
    advance_to_received,
    counts,
    event_path,
    get_loan,
    give_back,
    make_active_loan,
    request_loan,
    scalar,
    sql,
    transfer_of,
)

pytestmark = pytest.mark.integration

FULL_PATH = ["PREPARED", "DISPATCHED", "IN_TRANSIT", "RECEIVED"]


def fire(n, work):
    """Run work(i, client) in n threads released together; return the n results in order."""
    barrier = threading.Barrier(n)
    results: list = [None] * n
    errors: list = []

    def worker(i):
        try:
            client = TestClient(app, raise_server_exceptions=False)
            barrier.wait(timeout=15)
            results[i] = work(i, client)
        except BaseException as exc:  # surfaced below, in the main thread
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not any(t.is_alive() for t in threads), "a worker hung (possible deadlock)"
    assert not errors, errors
    return results


def inject_delay_before_copy_lock(monkeypatch, delays):
    """The k-th request to reach the copy lock sleeps delays[k] seconds first."""
    real = locks.lock_copy
    arrivals = itertools.count()
    guard = threading.Lock()

    def delayed(session, copy_id):
        with guard:
            k = next(arrivals)
        time.sleep(delays[k % len(delays)])
        return real(session, copy_id)

    monkeypatch.setattr("app.application.request_loan.lock_copy", delayed)


def slow_after(monkeypatch, dotted_name, seconds):
    """Make `dotted_name` sleep right AFTER it returns, i.e. after the row lock is taken and the
    state read. With correct locking the other requests queue behind it; without locking they
    would all read the same stale state inside the window and race."""
    module_name, attribute = dotted_name.rsplit(".", 1)
    real = getattr(importlib.import_module(module_name), attribute)

    def slow(*args, **kwargs):
        result = real(*args, **kwargs)
        time.sleep(seconds)
        return result

    monkeypatch.setattr(dotted_name, slow)


def codes(responses):
    return sorted(
        (r.status_code, r.json().get("error", {}).get("code") if r.status_code >= 400 else None)
        for r in responses
    )


# --- different Idempotency-Keys for the same copy: exactly one winner ------------------------


@pytest.mark.parametrize("n", [2, 5])
def test_distinct_keys_same_copy_have_one_winner(api, app_engine, n):
    responses = fire(n, lambda i, c: request_loan(c, f"key-{i}", member=i + 1, copy=1, dest=2))

    assert codes(responses) == [(201, None)] + [(409, "copy_not_available")] * (n - 1)
    winner = next(r for r in responses if r.status_code == 201).json()
    assert counts(app_engine) == {
        "loans": 1,
        "transfers": 1,
        "transfer_events": 1,
        "idempotency_records": 1,  # losers' claims rolled back with their transactions
    }
    assert scalar(app_engine, "SELECT status FROM copies WHERE id = 1") == "RESERVED"
    assert (
        scalar(
            app_engine,
            "SELECT count(*) FROM loans WHERE status IN ('REQUESTED','ACTIVE','RETURNING')",
        )
        == 1
    )
    assert scalar(app_engine, "SELECT id FROM loans") == winner["id"]
    assert (
        scalar(app_engine, "SELECT key FROM idempotency_records")
        == f"key-{winner['member_id'] - 1}"
    )


@pytest.mark.parametrize("delays", [(0.4, 0.0), (0.0, 0.4), (0.3, 0.0, 0.1), (0.1, 0.2, 0.0, 0.3)])
def test_distinct_keys_one_winner_even_with_injected_scheduler_delays(
    api, app_engine, monkeypatch, delays
):
    inject_delay_before_copy_lock(monkeypatch, delays)
    n = len(delays)
    responses = fire(n, lambda i, c: request_loan(c, f"key-{i}", member=i + 1, copy=1, dest=3))

    assert codes(responses) == [(201, None)] + [(409, "copy_not_available")] * (n - 1)
    assert counts(app_engine) == {
        "loans": 1,
        "transfers": 1,
        "transfer_events": 1,
        "idempotency_records": 1,
    }


def test_concurrent_requests_for_different_copies_do_not_block_each_other(api, app_engine):
    # copy 1 (branch 1) and copy 2 (branch 2) are independent resources: both succeed.
    responses = fire(
        2,
        lambda i, c: request_loan(c, f"key-{i}", member=i + 1, copy=i + 1, dest=3),
    )
    assert codes(responses) == [(201, None), (201, None)]
    assert counts(app_engine)["loans"] == 2


# --- the same Idempotency-Key and body: one resource, deterministic replay -------------------


@pytest.mark.parametrize("n", [2, 6])
def test_same_key_same_body_converges_on_one_resource(api, app_engine, n):
    responses = fire(n, lambda i, c: request_loan(c, "demo-req-001"))

    assert codes(responses) == [(200, None)] * (n - 1) + [(201, None)]
    assert len({r.json()["id"] for r in responses}) == 1  # everyone sees the same loan
    assert counts(app_engine) == {
        "loans": 1,
        "transfers": 1,
        "transfer_events": 1,
        "idempotency_records": 1,
    }


def test_same_key_same_body_with_the_winner_held_back_by_an_injected_delay(
    api, app_engine, monkeypatch
):
    """The first request holds its (uncommitted) claim for 0.5 s; the others must wait for it
    and then replay, never create a second loan and never see a half-written record."""
    inject_delay_before_copy_lock(monkeypatch, (0.5,))  # only the claim winner reaches the lock
    started = time.monotonic()
    responses = fire(4, lambda i, c: request_loan(c, "demo-req-001"))

    assert time.monotonic() - started >= 0.5
    assert codes(responses) == [(200, None)] * 3 + [(201, None)]
    assert len({r.json()["id"] for r in responses}) == 1
    assert counts(app_engine) == {
        "loans": 1,
        "transfers": 1,
        "transfer_events": 1,
        "idempotency_records": 1,
    }


def test_same_key_different_bodies_concurrently_one_creates_the_others_conflict(api, app_engine):
    responses = fire(3, lambda i, c: request_loan(c, "shared-key", member=i + 1))

    assert codes(responses) == [
        (201, None),
        (409, "idempotency_key_reuse"),
        (409, "idempotency_key_reuse"),
    ]
    assert counts(app_engine) == {
        "loans": 1,
        "transfers": 1,
        "transfer_events": 1,
        "idempotency_records": 1,
    }


def test_same_key_when_the_first_attempt_fails_validation_then_everyone_converges_on_the_failure(
    api, app_engine
):
    responses = fire(4, lambda i, c: request_loan(c, "bad-member-key", member=6))
    assert codes(responses) == [(409, "member_disabled")] * 4
    assert counts(app_engine) == {
        "loans": 0,
        "transfers": 0,
        "transfer_events": 0,
        "idempotency_records": 0,
    }


# --- simultaneous commands on an existing loan -------------------------------------------------


def test_simultaneous_advances_of_one_transfer_apply_exactly_once(api, app_engine, monkeypatch):
    slow_after(monkeypatch, "app.application.advance_transfer.lock_transfer", 0.2)
    loan = request_loan(api).json()
    out = transfer_of(loan, "OUTBOUND")["id"]

    responses = fire(4, lambda i, c: advance(c, out, "DISPATCHED"))

    assert codes(responses) == [(200, None)] + [(409, "illegal_transition")] * 3
    assert event_path(app_engine, out) == ["PREPARED", "DISPATCHED"]  # no duplicated event
    assert scalar(app_engine, "SELECT status FROM copies WHERE id = 1") == "IN_TRANSIT"


def test_simultaneous_duplicate_receipt_changes_state_once(api, app_engine, monkeypatch):
    slow_after(monkeypatch, "app.application.advance_transfer.lock_transfer", 0.2)
    loan = request_loan(api).json()
    out = transfer_of(loan, "OUTBOUND")["id"]
    for step in ("DISPATCHED", "IN_TRANSIT"):
        assert advance(api, out, step).status_code == 200

    responses = fire(4, lambda i, c: advance(c, out, "RECEIVED"))

    assert codes(responses) == [(200, None)] + [(409, "illegal_transition")] * 3
    assert event_path(app_engine, out) == FULL_PATH
    assert sql(app_engine, "SELECT status, current_branch_id FROM copies WHERE id = 1") == [
        ("RESERVED", 2)
    ]


def test_simultaneous_activation_succeeds_once(api, app_engine, monkeypatch):
    slow_after(monkeypatch, "app.application.activate_loan.lock_loan_transfer", 0.2)
    loan = request_loan(api).json()
    advance_to_received(api, transfer_of(loan, "OUTBOUND")["id"])
    responses = fire(3, lambda i, c: activate(c, loan["id"]))
    assert codes(responses) == [(200, None)] + [(409, "loan_not_requested")] * 2


def test_simultaneous_returns_create_a_single_return_transfer(api, app_engine, monkeypatch):
    slow_after(monkeypatch, "app.application.return_loan.lock_loan", 0.2)
    loan = make_active_loan(api)
    responses = fire(3, lambda i, c: give_back(c, loan["id"], "GOOD" if i == 0 else "DAMAGED"))

    assert codes(responses) == [(200, None)] + [(409, "loan_not_active")] * 2
    assert scalar(app_engine, "SELECT count(*) FROM transfers WHERE direction = 'RETURN'") == 1
    assert scalar(app_engine, "SELECT count(*) FROM loans WHERE status = 'RETURNING'") == 1


# --- stress: every command racing on one loan; no deadlock, consistent end state --------------


def test_mixed_commands_racing_on_one_loan_never_deadlock_and_end_consistent(
    api, app_engine, monkeypatch
):
    slow_after(monkeypatch, "app.application.advance_transfer.lock_transfer", 0.02)
    slow_after(monkeypatch, "app.application.activate_loan.lock_loan_transfer", 0.02)
    slow_after(monkeypatch, "app.application.return_loan.lock_loan", 0.02)
    loan_id = request_loan(api).json()["id"]
    outcomes: list[int] = []

    def drive(i, client):
        rng = random.Random(1234 + i)
        seen = []
        for _ in range(60):
            loan = client.get(f"{API}/loans/{loan_id}").json()
            if loan["status"] == "CLOSED":
                break
            actions = [
                lambda t=t["id"], s=s: advance(client, t, s)
                for t in loan["transfers"]
                for s in ("DISPATCHED", "IN_TRANSIT", "RECEIVED")
            ] + [lambda: activate(client, loan_id), lambda: give_back(client, loan_id, "GOOD")]
            rng.shuffle(actions)
            seen.extend(action().status_code for action in actions)
        outcomes.extend(seen)

    fire(4, drive)

    assert outcomes and set(outcomes) <= {200, 409}, set(outcomes)  # no 500 (lock timeout/deadlock)
    final = get_loan(api, loan_id)
    assert final["status"] == "CLOSED"
    assert [t["direction"] for t in final["transfers"]] == ["OUTBOUND", "RETURN"]
    for transfer in final["transfers"]:
        assert transfer["status"] == "RECEIVED"
        assert (
            event_path(app_engine, transfer["id"]) == FULL_PATH
        )  # each state exactly once, in order
    assert sql(app_engine, "SELECT status, current_branch_id FROM copies WHERE id = 1") == [
        ("AVAILABLE", 1)
    ]
    assert counts(app_engine)["loans"] == 1
