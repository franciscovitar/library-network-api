"""Full interlibrary loan lifecycle through the HTTP API against real PostgreSQL.

Seed reference: branches 1-3 (Central/North/South), members 1-6 (6 disabled), copy 1 is owned by
branch 1, copy 2 by branch 2, copy 10 is RETIRED.
"""

from datetime import timedelta

import pytest

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
    transfer_of,
)

pytestmark = pytest.mark.integration

FULL_PATH = ["PREPARED", "DISPATCHED", "IN_TRANSIT", "RECEIVED"]


def copy_json(api, copy_id=1):
    return api.get(f"{API}/copies/{copy_id}").json()


def assert_copy(api, *, status, branch, copy_id=1):
    copy = copy_json(api, copy_id)
    assert (copy["status"], copy["current_branch_id"]) == (status, branch), copy


# --- the happy path, step by step (GOOD return) ----------------------------------------------


def test_full_roundtrip_good_return(api, app_engine, clock):
    # 1. request: loan REQUESTED + outward PREPARED transfer + RESERVED copy, atomically
    created = request_loan(api, "demo-req-001")
    assert created.status_code == 201, created.text
    loan = created.json()
    assert loan["status"] == "REQUESTED"
    assert (loan["origin_branch_id"], loan["destination_branch_id"]) == (1, 2)
    out = transfer_of(loan, "OUTBOUND")
    assert (out["status"], out["origin_branch_id"], out["destination_branch_id"]) == (
        "PREPARED",
        1,
        2,
    )
    assert_copy(api, status="RESERVED", branch=1)
    assert event_path(app_engine, out["id"]) == ["PREPARED"]

    # 2. outward dispatch: copy IN_TRANSIT but its location does not change yet
    assert advance(api, out["id"], "DISPATCHED").status_code == 200
    assert_copy(api, status="IN_TRANSIT", branch=1)
    assert advance(api, out["id"], "IN_TRANSIT").status_code == 200
    assert_copy(api, status="IN_TRANSIT", branch=1)

    # 3. outward receipt: location changes to the destination, copy RESERVED there
    received = advance(api, out["id"], "RECEIVED")
    assert received.status_code == 200
    assert received.json()["received_at"] is not None
    assert [e["to_status"] for e in received.json()["events"]] == FULL_PATH
    assert_copy(api, status="RESERVED", branch=2)

    # 4. activate: ACTIVE, ON_LOAN, due 14 days after start
    clock.advance(hours=3)
    active = activate(api, loan["id"])
    assert active.status_code == 200, active.text
    body = active.json()
    assert body["status"] == "ACTIVE"
    assert body["due_at"] is not None and body["started_at"] is not None
    assert_copy(api, status="ON_LOAN", branch=2)

    # 5. borrower hands the copy back: RETURNING + PENDING_RETURN + RETURN transfer PREPARED
    clock.advance(days=5)
    returned = give_back(api, loan["id"], "GOOD")
    assert returned.status_code == 200, returned.text
    body = returned.json()
    assert (body["status"], body["return_condition"]) == ("RETURNING", "GOOD")
    assert body["closed_at"] is None and body["borrower_returned_at"] is not None
    ret = transfer_of(body, "RETURN")
    assert (ret["status"], ret["origin_branch_id"], ret["destination_branch_id"]) == (
        "PREPARED",
        2,
        1,
    )
    assert_copy(api, status="PENDING_RETURN", branch=2)

    # nobody can request the copy while it is being returned (nonterminal loan, not AVAILABLE)
    blocked = request_loan(api, "other-key", member=2, dest=3)
    assert (blocked.status_code, blocked.json()["error"]["code"]) == (409, "copy_not_available")

    # 6. return dispatch: copy IN_TRANSIT, location still the destination until reception
    assert advance(api, ret["id"], "DISPATCHED").status_code == 200
    assert_copy(api, status="IN_TRANSIT", branch=2)
    assert request_loan(api, "other-key-2", member=2, dest=3).status_code == 409
    assert get_loan(api, loan["id"])["status"] == "RETURNING"  # not closed by transit
    assert advance(api, ret["id"], "IN_TRANSIT").status_code == 200
    assert get_loan(api, loan["id"])["status"] == "RETURNING"

    # 7. return reception at the owning branch: copy AVAILABLE there, loan CLOSED
    clock.advance(days=1)
    assert advance(api, ret["id"], "RECEIVED").status_code == 200
    final = get_loan(api, loan["id"])
    assert final["status"] == "CLOSED" and final["closed_at"] is not None
    assert_copy(api, status="AVAILABLE", branch=1)
    assert copy_json(api)["physical_condition"] == "GOOD"
    assert all(t["status"] == "RECEIVED" for t in final["transfers"])
    assert event_path(app_engine, out["id"]) == FULL_PATH
    assert event_path(app_engine, ret["id"]) == FULL_PATH

    # the due date is exactly 14 days after activation (injected clock, no sleeping)
    started, due = body["started_at"], body["due_at"]
    assert due != started
    assert scalar(app_engine, "SELECT due_at - started_at FROM loans") == timedelta(days=14)

    # a completed loan no longer blocks the copy: it can be requested again
    again = request_loan(api, "second-loan", member=3, dest=3)
    assert again.status_code == 201, again.text
    assert again.json()["id"] != loan["id"]


def test_damaged_return_retires_the_copy_only_on_final_reception(api, app_engine):
    loan = make_active_loan(api)
    returned = give_back(api, loan["id"], "DAMAGED").json()
    ret = transfer_of(returned, "RETURN")
    assert returned["return_condition"] == "DAMAGED"
    # borrower hand-back alone never retires or releases the copy
    assert_copy(api, status="PENDING_RETURN", branch=2)

    for status in ("DISPATCHED", "IN_TRANSIT"):
        assert advance(api, ret["id"], status).status_code == 200
        assert copy_json(api)["status"] == "IN_TRANSIT"
    assert advance(api, ret["id"], "RECEIVED").status_code == 200

    copy = copy_json(api)
    assert (copy["status"], copy["current_branch_id"], copy["physical_condition"]) == (
        "RETIRED",
        1,
        "DAMAGED",
    )
    assert get_loan(api, loan["id"])["status"] == "CLOSED"
    # a retired copy is never requestable again
    again = request_loan(api, "after-damage", member=2, dest=3)
    assert (again.status_code, again.json()["error"]["code"]) == (409, "copy_not_available")
    assert counts(app_engine)["loans"] == 1


def test_nonterminal_loan_count_follows_the_lifecycle(api, app_engine):
    query = "SELECT count(*) FROM loans WHERE status IN ('REQUESTED','ACTIVE','RETURNING')"
    loan = make_active_loan(api)
    assert scalar(app_engine, query) == 1
    ret = transfer_of(give_back(api, loan["id"]).json(), "RETURN")
    assert scalar(app_engine, query) == 1  # RETURNING is still nonterminal
    advance_to_received(api, ret["id"])
    assert scalar(app_engine, query) == 0


# --- invalid requests and state errors; nothing may change ------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "status", "code"),
    [
        (dict(copy=999), 404, "copy_not_found"),
        (dict(member=999), 404, "member_not_found"),
        (dict(dest=999), 404, "branch_not_found"),
        (dict(member=6), 409, "member_disabled"),
        (dict(copy=10), 409, "copy_not_available"),  # retired copy
        (dict(dest=1), 409, "same_branch"),  # copy 1 is owned by branch 1
    ],
)
def test_rejected_requests_write_nothing(api, app_engine, kwargs, status, code):
    before = counts(app_engine)
    response = request_loan(api, "will-fail", **kwargs)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert (
        counts(app_engine)
        == before
        == {
            "loans": 0,
            "transfers": 0,
            "transfer_events": 0,
            "idempotency_records": 0,
        }
    )
    assert copy_json(api, 1)["status"] == "AVAILABLE"


def test_request_to_an_inactive_branch_is_rejected(api, app_engine):
    with app_engine.begin() as conn:
        conn.exec_driver_sql("UPDATE branches SET active = false WHERE id = 2")
    response = request_loan(api, "inactive", dest=2)
    assert (response.status_code, response.json()["error"]["code"]) == (409, "branch_inactive")
    assert counts(app_engine)["loans"] == 0


@pytest.mark.parametrize(
    ("headers", "body"),
    [
        ({}, {"member_id": 1, "copy_id": 1, "destination_branch_id": 2}),  # missing key
        ({"Idempotency-Key": "k"}, {"member_id": 1, "copy_id": 1}),  # missing field
        ({"Idempotency-Key": "k"}, {"member_id": 0, "copy_id": 1, "destination_branch_id": 2}),
        ({"Idempotency-Key": "k"}, {"member_id": "x", "copy_id": 1, "destination_branch_id": 2}),
        (
            {"Idempotency-Key": "k"},  # unknown field: no mass assignment
            {"member_id": 1, "copy_id": 1, "destination_branch_id": 2, "status": "ACTIVE"},
        ),
        (
            {"Idempotency-Key": "k" * 129},
            {"member_id": 1, "copy_id": 1, "destination_branch_id": 2},
        ),
    ],
)
def test_invalid_payloads_return_422_with_a_stable_error_code(api, app_engine, headers, body):
    response = api.post(f"{API}/loans/interlibrary", json=body, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert counts(app_engine)["loans"] == 0


def test_illegal_transfer_transitions_are_rejected_without_side_effects(api, app_engine):
    loan = request_loan(api).json()
    out = transfer_of(loan, "OUTBOUND")["id"]
    snapshot = (counts(app_engine), copy_json(api))

    for target in ("IN_TRANSIT", "RECEIVED", "PREPARED"):  # skip ahead / no-op
        response = advance(api, out, target)
        assert (response.status_code, response.json()["error"]["code"]) == (
            409,
            "illegal_transition",
        )
    assert (counts(app_engine), copy_json(api)) == snapshot

    assert advance(api, out, "DISPATCHED").status_code == 200
    snapshot = (counts(app_engine), copy_json(api))
    for target in ("PREPARED", "DISPATCHED", "RECEIVED"):  # backtrack / repeat / skip
        assert advance(api, out, target).status_code == 409
    assert (counts(app_engine), copy_json(api)) == snapshot

    unknown = advance(api, out, "LOST")
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (422, "validation_error")
    assert advance(api, 99999, "DISPATCHED").status_code == 404


def test_duplicate_receive_does_not_duplicate_history(api, app_engine):
    loan = request_loan(api).json()
    out = transfer_of(loan, "OUTBOUND")["id"]
    advance_to_received(api, out)
    before = counts(app_engine)
    duplicate = advance(api, out, "RECEIVED")
    assert (duplicate.status_code, duplicate.json()["error"]["code"]) == (409, "illegal_transition")
    assert counts(app_engine) == before
    assert event_path(app_engine, out) == FULL_PATH
    assert_copy(api, status="RESERVED", branch=2)


def test_activation_requires_the_outward_transfer_to_be_received(api, app_engine):
    loan = request_loan(api).json()
    out = transfer_of(loan, "OUTBOUND")["id"]
    for status in ("DISPATCHED", "IN_TRANSIT"):
        assert advance(api, out, status).status_code == 200
        early = activate(api, loan["id"])
        assert (early.status_code, early.json()["error"]["code"]) == (409, "transfer_not_received")
    assert get_loan(api, loan["id"])["status"] == "REQUESTED"
    assert_copy(api, status="IN_TRANSIT", branch=1)


def test_activation_is_rejected_if_the_member_was_disabled_meanwhile(api, app_engine):
    loan = request_loan(api).json()
    advance_to_received(api, transfer_of(loan, "OUTBOUND")["id"])
    with app_engine.begin() as conn:
        conn.exec_driver_sql("UPDATE members SET enabled = false WHERE id = 1")
    response = activate(api, loan["id"])
    assert (response.status_code, response.json()["error"]["code"]) == (409, "member_disabled")
    assert get_loan(api, loan["id"])["status"] == "REQUESTED"
    assert get_loan(api, loan["id"])["started_at"] is None
    assert_copy(api, status="RESERVED", branch=2)


def test_activation_can_only_happen_once(api):
    loan = make_active_loan(api)
    again = activate(api, loan["id"])
    assert (again.status_code, again.json()["error"]["code"]) == (409, "loan_not_requested")


def test_return_rules(api, app_engine):
    loan = request_loan(api).json()
    early = give_back(api, loan["id"])  # loan not active yet
    assert (early.status_code, early.json()["error"]["code"]) == (409, "loan_not_active")

    advance_to_received(api, transfer_of(loan, "OUTBOUND")["id"])
    assert give_back(api, loan["id"]).status_code == 409  # still REQUESTED
    assert activate(api, loan["id"]).status_code == 200

    bad = api.post(f"{API}/loans/{loan['id']}/return", json={"condition": "LOST"})
    assert (bad.status_code, bad.json()["error"]["code"]) == (422, "validation_error")
    assert get_loan(api, loan["id"])["status"] == "ACTIVE"

    assert give_back(api, loan["id"], "GOOD").status_code == 200
    twice = give_back(api, loan["id"], "DAMAGED")
    assert (twice.status_code, twice.json()["error"]["code"]) == (409, "loan_not_active")
    # exactly one return transfer, and the first condition stands
    assert scalar(app_engine, "SELECT count(*) FROM transfers WHERE direction = 'RETURN'") == 1
    assert get_loan(api, loan["id"])["return_condition"] == "GOOD"
    assert activate(api, 99999).status_code == 404
    assert give_back(api, 99999).status_code == 404


def test_return_transfer_cannot_move_before_the_loan_is_returning(api):
    """The RETURN transfer only exists after the borrower returns; its steps need RETURNING."""
    loan = make_active_loan(api)
    ret = transfer_of(give_back(api, loan["id"]).json(), "RETURN")["id"]
    assert advance(api, ret, "RECEIVED").status_code == 409  # cannot skip
    assert get_loan(api, loan["id"])["status"] == "RETURNING"


# --- reads ----------------------------------------------------------------------------------


def test_read_endpoints(api):
    branches = api.get(f"{API}/branches").json()
    assert [b["name"] for b in branches] == ["Central Branch", "North Branch", "South Branch"]

    page = api.get(f"{API}/books", params={"limit": 2, "offset": 1}).json()
    assert (page["limit"], page["offset"], page["total"]) == (2, 1, 5)
    assert [b["id"] for b in page["items"]] == [2, 3]
    assert api.get(f"{API}/books", params={"limit": 100}).status_code == 200
    for params in ({"limit": 101}, {"limit": 0}, {"offset": -1}):  # bounded pagination
        assert api.get(f"{API}/books", params=params).status_code == 422

    for path, code in (
        ("copies/999", "copy_not_found"),
        ("loans/999", "loan_not_found"),
        ("transfers/999", "transfer_not_found"),
    ):
        response = api.get(f"{API}/{path}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == code
