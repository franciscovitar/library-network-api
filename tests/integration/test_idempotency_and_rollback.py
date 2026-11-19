"""Idempotent requests (sequential) and all-or-nothing behaviour under injected failures."""

import json

import pytest

from tests.integration.helpers import (
    API,
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

ONE_OF_EACH = {"loans": 1, "transfers": 1, "transfer_events": 1, "idempotency_records": 1}


# --- idempotency ------------------------------------------------------------------------------


def test_same_key_and_body_replays_the_first_result(api, app_engine):
    first = request_loan(api, "demo-req-001")
    replay = request_loan(api, "demo-req-001")
    assert (first.status_code, replay.status_code) == (201, 200)
    assert replay.json()["id"] == first.json()["id"]
    assert replay.json() == first.json()
    assert counts(app_engine) == ONE_OF_EACH  # no duplicate loan, transfer, event or record


def test_replay_returns_the_same_resource_even_after_it_advanced(api, app_engine):
    first = request_loan(api, "demo-req-001").json()
    advance_to_received(api, transfer_of(first, "OUTBOUND")["id"])
    replay = request_loan(api, "demo-req-001")
    assert replay.status_code == 200
    assert replay.json()["id"] == first["id"]  # same identity; current state is reflected
    assert counts(app_engine)["loans"] == 1


def test_json_key_order_does_not_change_the_canonical_hash(api, app_engine):
    headers = {"Idempotency-Key": "ordering", "Content-Type": "application/json"}
    a = api.post(
        f"{API}/loans/interlibrary",
        content=json.dumps({"member_id": 1, "copy_id": 1, "destination_branch_id": 2}),
        headers=headers,
    )
    b = api.post(
        f"{API}/loans/interlibrary",
        content=json.dumps({"destination_branch_id": 2, "copy_id": 1, "member_id": 1}),
        headers=headers,
    )
    assert (a.status_code, b.status_code) == (201, 200)
    assert counts(app_engine)["loans"] == 1


@pytest.mark.parametrize("changed", [dict(member=2), dict(dest=3), dict(copy=3)])
def test_same_key_with_a_different_body_is_a_conflict(api, app_engine, changed):
    assert request_loan(api, "demo-req-001").status_code == 201
    response = request_loan(api, "demo-req-001", **changed)
    assert (response.status_code, response.json()["error"]["code"]) == (
        409,
        "idempotency_key_reuse",
    )
    assert counts(app_engine) == ONE_OF_EACH


def test_a_rejected_request_does_not_consume_its_key(api, app_engine):
    """The key claim rolls back with the failed request, so a corrected retry may reuse it."""
    rejected = request_loan(api, "reused", member=6)  # disabled member
    assert rejected.status_code == 409
    assert counts(app_engine)["idempotency_records"] == 0
    retry = request_loan(api, "reused", member=1)
    assert retry.status_code == 201
    assert counts(app_engine) == ONE_OF_EACH


def test_different_keys_are_independent_operations(api, app_engine):
    assert request_loan(api, "key-a", copy=1, member=1).status_code == 201
    assert request_loan(api, "key-b", copy=2, member=1, dest=3).status_code == 201
    assert scalar(app_engine, "SELECT count(DISTINCT key) FROM idempotency_records") == 2


# --- rollback under injected failures ---------------------------------------------------------


def snapshot(engine):
    return (
        counts(engine),
        sql(
            engine,
            "SELECT id, status, current_branch_id, physical_condition FROM copies ORDER BY id",
        ),
        sql(engine, "SELECT id, status, closed_at, return_condition FROM loans ORDER BY id"),
        sql(engine, "SELECT id, status, received_at FROM transfers ORDER BY id"),
    )


def explode(*_args, **_kwargs):
    raise RuntimeError("boom: injected failure with secret-internal-detail")


def test_failure_while_requesting_rolls_back_loan_transfer_and_key_claim(
    api, app_engine, monkeypatch
):
    before = snapshot(app_engine)
    # Fails AFTER the key claim, the copy lock, the loan and the transfer were already written.
    monkeypatch.setattr("app.application.request_loan._add_initial_history", explode)
    response = request_loan(api, "will-roll-back")
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Unexpected internal error."}
    }
    assert "boom" not in response.text and "secret" not in response.text  # sanitized
    assert snapshot(app_engine) == before
    assert counts(app_engine) == {
        "loans": 0,
        "transfers": 0,
        "transfer_events": 0,
        "idempotency_records": 0,
    }

    monkeypatch.undo()  # the same key is usable again: the claim never committed
    assert request_loan(api, "will-roll-back").status_code == 201
    assert counts(app_engine) == ONE_OF_EACH


@pytest.mark.parametrize("step", ["DISPATCHED", "IN_TRANSIT", "RECEIVED"])
def test_failure_in_an_outward_transition_rolls_back_every_row(api, app_engine, monkeypatch, step):
    loan = request_loan(api).json()
    out = transfer_of(loan, "OUTBOUND")["id"]
    order = ["DISPATCHED", "IN_TRANSIT", "RECEIVED"]
    for done in order[: order.index(step)]:
        assert advance(api, out, done).status_code == 200
    before = snapshot(app_engine)

    # Fails after the transfer, copy (and, on RECEIVED, its location) were updated and flushed.
    monkeypatch.setattr("app.application.advance_transfer._append_event", explode)
    assert advance(api, out, step).status_code == 500
    assert snapshot(app_engine) == before
    monkeypatch.undo()

    assert advance(api, out, step).status_code == 200  # the step still works afterwards
    assert event_path(app_engine, out)[-1] == step


def test_failure_on_the_final_return_reception_keeps_loan_copy_and_transfer_consistent(
    api, app_engine, monkeypatch
):
    loan = make_active_loan(api)
    ret = transfer_of(give_back(api, loan["id"], "DAMAGED").json(), "RETURN")["id"]
    for step in ("DISPATCHED", "IN_TRANSIT"):
        assert advance(api, ret, step).status_code == 200
    before = snapshot(app_engine)

    monkeypatch.setattr("app.application.advance_transfer._append_event", explode)
    assert advance(api, ret, "RECEIVED").status_code == 500
    assert snapshot(app_engine) == before
    # nothing half-applied: loan not closed, copy not retired/relocated, no RECEIVED event
    assert get_loan(api, loan["id"])["status"] == "RETURNING"
    assert sql(app_engine, "SELECT status, current_branch_id FROM copies WHERE id = 1") == [
        ("IN_TRANSIT", 2)
    ]
    assert event_path(app_engine, ret) == ["PREPARED", "DISPATCHED", "IN_TRANSIT"]


def test_failure_while_returning_leaves_the_loan_active(api, app_engine, monkeypatch):
    loan = make_active_loan(api)
    before = snapshot(app_engine)
    monkeypatch.setattr("app.application.return_loan._add_initial_history", explode)
    assert give_back(api, loan["id"], "GOOD").status_code == 500
    assert snapshot(app_engine) == before
    assert get_loan(api, loan["id"])["status"] == "ACTIVE"
    assert scalar(app_engine, "SELECT count(*) FROM transfers WHERE direction = 'RETURN'") == 0
    monkeypatch.undo()
    assert give_back(api, loan["id"], "GOOD").status_code == 200
