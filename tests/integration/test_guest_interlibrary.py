"""Interlibrary guest flow: real PostgreSQL transitions and cross-visitor denials."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.main import app
from app.security import verified_subject
from tests.integration.helpers import scalar

pytestmark = pytest.mark.integration
BASE = "/api/v2/guest"


def identity(subject: str) -> None:
    app.dependency_overrides[verified_subject] = lambda: subject


def bootstrap(api, subject: str):
    identity(subject)
    response = api.post(f"{BASE}/start")
    assert response.status_code == 201, response.text
    return response.json()


def guest_subject() -> str:
    return f"guest:{uuid4()}"


def details(api, loan_id):
    response = api.get(f"{BASE}/loans/{loan_id}")
    assert response.status_code == 200, response.text
    return response.json()


def next_step(api, transfer_id, state):
    return api.post(
        f"{BASE}/transfers/{transfer_id}/transitions",
        json={"next_status": state},
    )


def test_interlibrary_roundtrip_is_transactional_and_scoped(api, app_engine):
    a, b = guest_subject(), guest_subject()
    a_profile = bootstrap(api, a)
    b_profile = bootstrap(api, b)
    a_origin, a_destination = [x["branch_id"] for x in a_profile["branches"]]
    b_origin = b_profile["branches"][0]["branch_id"]
    identity(a)
    member = api.get(f"{BASE}/members").json()[0]["id"]
    copy = api.get(f"{BASE}/branches/{a_origin}/copies").json()["items"][0]["id"]
    posted = api.post(
        f"{BASE}/loans/interlibrary",
        json={"member_id": member, "copy_id": copy, "destination_branch_id": a_destination},
        headers={"Idempotency-Key": "roundtrip-one"},
    )
    assert posted.status_code == 201, posted.text
    loan = posted.json()
    assert loan["kind"] == "INTERLIBRARY" and loan["status"] == "REQUESTED"
    outbound = loan["transfers"][0]
    assert outbound["status"] == "PREPARED"
    assert outbound["origin_branch_id"] == a_origin
    assert outbound["destination_branch_id"] == a_destination
    assert len(loan["transfers"]) == 1

    # Every object is tenant-owned. The second guest cannot enumerate or mutate it.
    identity(b)
    assert api.get(f"{BASE}/loans/{loan['id']}").status_code == 404
    assert api.get(f"{BASE}/transfers/{outbound['id']}").status_code == 404
    assert next_step(api, outbound["id"], "DISPATCHED").status_code == 404
    assert api.post(f"{BASE}/loans/{loan['id']}/activate").status_code == 404
    assert (
        api.post(f"{BASE}/loans/{loan['id']}/return", json={"condition": "GOOD"}).status_code == 404
    )
    assert api.get(f"{BASE}/loans").json() == []
    assert api.get(f"{BASE}/branches/{b_origin}/overview").json()["active_loans"] == 0

    identity(a)
    assert api.post(f"{BASE}/loans/{loan['id']}/activate").status_code == 409
    assert next_step(api, outbound["id"], "RECEIVED").status_code == 409

    retry = api.post(
        f"{BASE}/loans/interlibrary",
        json={"member_id": member, "copy_id": copy, "destination_branch_id": a_destination},
        headers={"Idempotency-Key": "roundtrip-one"},
    )
    assert retry.status_code == 200 and retry.json()["id"] == loan["id"]

    for state in ("DISPATCHED", "IN_TRANSIT", "RECEIVED"):
        moved = next_step(api, outbound["id"], state)
        assert moved.status_code == 200, moved.text
        assert moved.json()["status"] == state
    assert next_step(api, outbound["id"], "RECEIVED").status_code == 409
    history = api.get(f"{BASE}/transfers/{outbound['id']}")
    assert [event["to_status"] for event in history.json()["events"]] == [
        "PREPARED",
        "DISPATCHED",
        "IN_TRANSIT",
        "RECEIVED",
    ]
    active = api.post(f"{BASE}/loans/{loan['id']}/activate")
    assert active.status_code == 200, active.text
    assert active.json()["status"] == "ACTIVE"
    assert api.get(f"{BASE}/branches/{a_destination}/overview").json()["active_loans"] == 1

    returned = api.post(f"{BASE}/loans/{loan['id']}/return", json={"condition": "GOOD"})
    assert returned.status_code == 200, returned.text
    assert returned.json()["status"] == "RETURNING"
    ret = next(t for t in returned.json()["transfers"] if t["direction"] == "RETURN")
    assert ret["origin_branch_id"] == a_destination
    assert ret["destination_branch_id"] == a_origin
    for state in ("DISPATCHED", "IN_TRANSIT", "RECEIVED"):
        result = next_step(api, ret["id"], state)
        assert result.status_code == 200, result.text
    final = details(api, loan["id"])
    assert final["status"] == "CLOSED"
    assert final["closed_at"] is not None
    assert len(final["transfers"]) == 2
    assert api.get(f"{BASE}/branches/{a_origin}/overview").json()["available_copies"] == 3
    assert api.get(f"{BASE}/loans").json()[0]["id"] == loan["id"]
    assert scalar(app_engine, "SELECT count(*) FROM loans") == 1
    assert scalar(app_engine, "SELECT count(*) FROM transfers") == 2
    assert scalar(app_engine, "SELECT count(*) FROM transfer_events") == 8
    with app_engine.connect() as conn:
        current = conn.execute(
            text("SELECT status, current_branch_id FROM copies WHERE id=:id"),
            {"id": copy},
        ).one()
    assert current == ("AVAILABLE", a_origin)


def test_cross_workspace_request_and_transfer_ids_never_write(api, app_engine):
    a, b = guest_subject(), guest_subject()
    aa = bootstrap(api, a)
    bb = bootstrap(api, b)
    a1, a2 = [x["branch_id"] for x in aa["branches"]]
    b1, b2 = [x["branch_id"] for x in bb["branches"]]
    identity(a)
    member = api.get(f"{BASE}/members").json()[0]["id"]
    acopy = api.get(f"{BASE}/branches/{a1}/copies").json()["items"][0]["id"]
    identity(b)
    bmember = api.get(f"{BASE}/members").json()[0]["id"]
    bcopy = api.get(f"{BASE}/branches/{b1}/copies").json()["items"][0]["id"]
    identity(a)
    for member_id, copy_id, destination in (
        (member, acopy, b2),
        (bmember, acopy, a2),
        (member, bcopy, a2),
    ):
        denied = api.post(
            f"{BASE}/loans/interlibrary",
            json={
                "member_id": member_id,
                "copy_id": copy_id,
                "destination_branch_id": destination,
            },
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert denied.status_code == 404, denied.text
    assert scalar(app_engine, "SELECT count(*) FROM loans") == 0
    assert scalar(app_engine, "SELECT count(*) FROM transfers") == 0
    assert scalar(app_engine, "SELECT count(*) FROM idempotency_records") == 0


def test_interlibrary_replay_survives_quota_and_rejects_changed_body(api, app_engine, monkeypatch):
    from app.application import guest_workspace as guest_module

    monkeypatch.setattr(guest_module, "MAX_GUEST_LOANS", 1)
    subject = guest_subject()
    info = bootstrap(api, subject)
    origin, dest = [x["branch_id"] for x in info["branches"]]
    identity(subject)
    member = api.get(f"{BASE}/members").json()[0]["id"]
    copies = api.get(f"{BASE}/branches/{origin}/copies").json()["items"]
    payload = {"member_id": member, "copy_id": copies[0]["id"], "destination_branch_id": dest}
    first = api.post(
        f"{BASE}/loans/interlibrary",
        json=payload,
        headers={"Idempotency-Key": "same-key"},
    )
    assert first.status_code == 201, first.text
    exact = api.post(
        f"{BASE}/loans/interlibrary",
        json=payload,
        headers={"Idempotency-Key": "same-key"},
    )
    assert exact.status_code == 200 and exact.json()["id"] == first.json()["id"]
    altered = api.post(
        f"{BASE}/loans/interlibrary",
        json=payload | {"copy_id": copies[1]["id"]},
        headers={"Idempotency-Key": "same-key"},
    )
    assert altered.status_code == 409
    limited = api.post(
        f"{BASE}/loans/interlibrary",
        json=payload | {"copy_id": copies[1]["id"]},
        headers={"Idempotency-Key": "new-key"},
    )
    assert limited.status_code == 429
    assert scalar(app_engine, "SELECT count(*) FROM loans") == 1
