"""Local circulation against real PostgreSQL and the actual FastAPI route handlers."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.integration.helpers import API, counts, get_loan, request_loan, scalar

pytestmark = pytest.mark.integration


def issue(api, *, key="local-001", member=1, copy=1, branch=1):
    return api.post(
        f"{API}/loans/local",
        json={"member_id": member, "copy_id": copy, "branch_id": branch},
        headers={"Idempotency-Key": key},
    )


def checkin(api, loan_id, *, branch=1, condition="GOOD"):
    return api.post(
        f"{API}/loans/{loan_id}/local-return",
        json={"branch_id": branch, "condition": condition},
    )


def test_local_roundtrip_persists_without_transfers(api, app_engine, clock):
    created = issue(api)
    assert created.status_code == 201, created.text
    loan = created.json()
    assert (loan["kind"], loan["status"]) == ("LOCAL", "ACTIVE")
    assert (loan["origin_branch_id"], loan["destination_branch_id"]) == (1, 1)
    assert loan["transfers"] == []
    assert scalar(app_engine, "SELECT status FROM copies WHERE id = 1") == "ON_LOAN"
    assert scalar(
        app_engine, "SELECT due_at - started_at FROM loans WHERE id = :id", id=loan["id"]
    ) == timedelta(days=14)

    clock.advance(days=2)
    returned = checkin(api, loan["id"])
    assert returned.status_code == 200, returned.text
    assert (returned.json()["status"], returned.json()["return_condition"]) == ("CLOSED", "GOOD")
    assert returned.json()["closed_at"] is not None
    assert scalar(app_engine, "SELECT status FROM copies WHERE id = 1") == "AVAILABLE"
    assert scalar(app_engine, "SELECT count(*) FROM transfers") == 0

    second = issue(api, key="local-002", member=2)
    assert second.status_code == 201, second.text
    assert second.json()["id"] != loan["id"]


def test_local_damage_retires_copy(api, app_engine):
    loan = issue(api, key="local-damage", copy=1).json()
    r = checkin(api, loan["id"], condition="DAMAGED")
    assert r.status_code == 200, r.text
    assert scalar(app_engine, "SELECT status FROM copies WHERE id = 1") == "RETIRED"
    assert scalar(app_engine, "SELECT physical_condition FROM copies WHERE id = 1") == "DAMAGED"
    blocked = issue(api, key="try-damaged", member=2)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "copy_not_available"


def test_local_idempotency_replays_and_rejects_payload_changes(api, app_engine):
    first = issue(api, key="stable")
    replay = issue(api, key="stable")
    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    conflict = issue(api, key="stable", member=2)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_key_reuse"
    assert counts(app_engine) == {
        "loans": 1,
        "transfers": 0,
        "transfer_events": 0,
        "idempotency_records": 1,
    }


def test_local_conflicts_preserve_every_table(api, app_engine):
    baseline = counts(app_engine)
    bad_branch = issue(api, key="wrong-branch", branch=2)
    assert bad_branch.status_code == 409
    assert bad_branch.json()["error"]["code"] == "copy_not_at_branch"
    disabled = issue(api, key="disabled-member", member=6)
    assert disabled.status_code == 409
    assert disabled.json()["error"]["code"] == "member_disabled"
    unavailable = issue(api, key="retired", copy=10)
    assert unavailable.status_code == 409
    assert unavailable.json()["error"]["code"] == "copy_not_available"
    assert counts(app_engine) == baseline


def test_return_must_be_at_correct_branch_and_cannot_repeat(api, app_engine):
    loan = issue(api).json()
    prior = counts(app_engine)
    wrong = checkin(api, loan["id"], branch=2)
    assert wrong.status_code == 409
    assert wrong.json()["error"]["code"] == "wrong_branch"
    assert counts(app_engine) == prior
    assert checkin(api, loan["id"]).status_code == 200
    again = checkin(api, loan["id"])
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "loan_not_active"


def test_interlibrary_and_local_loan_flows_cannot_be_mixed(api, app_engine):
    inter = request_loan(api, "inter", member=1, copy=1, dest=2)
    assert inter.status_code == 201, inter.text
    inter_id = inter.json()["id"]
    assert get_loan(api, inter_id)["kind"] == "INTERLIBRARY"
    wrong = checkin(api, inter_id)
    assert wrong.status_code == 409
    assert wrong.json()["error"]["code"] == "wrong_loan_kind"
    assert issue(api, key="local-after-inter", member=2).status_code == 409
    assert counts(app_engine)["loans"] == 1


def test_local_loan_cannot_take_a_copy_reserved_by_another_operator(api):
    first = issue(api, key="first-operator")
    assert first.status_code == 201
    second = issue(api, key="second-operator", member=2)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "copy_not_available"


def test_missing_idempotency_header_is_validation_error(api):
    response = api.post(
        f"{API}/loans/local",
        json={"member_id": 1, "copy_id": 1, "branch_id": 1},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_openapi_exposes_local_operations():
    client = TestClient(app)
    paths = client.get("/openapi.json").json()["paths"]
    assert "post" in paths["/api/v1/loans/local"]
    assert "post" in paths["/api/v1/loans/{loan_id}/local-return"]


def test_concurrent_local_and_interlibrary_requests_share_the_copy_lock(api, app_engine):
    barrier = Barrier(2)

    def submit(kind):
        with TestClient(app, raise_server_exceptions=False) as client:
            barrier.wait(timeout=20)
            if kind == "local":
                return issue(client, key="race-local", member=1)
            return request_loan(client, "race-inter", member=2, copy=1, dest=2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, ["local", "interlibrary"]))
    assert sorted(result.status_code for result in outcomes) == [201, 409]
    assert scalar(app_engine, "SELECT count(*) FROM loans") == 1
    assert scalar(app_engine, "SELECT count(*) FROM idempotency_records") == 1
    assert scalar(app_engine, "SELECT status FROM copies WHERE id = 1") in {
        "ON_LOAN",
        "RESERVED",
    }


def test_same_local_key_concurrently_creates_only_one_loan(api, app_engine):
    barrier = Barrier(2)

    def submit(_index):
        with TestClient(app, raise_server_exceptions=False) as client:
            barrier.wait(timeout=20)
            return issue(client, key="parallel-replay")

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, range(2)))
    assert sorted(result.status_code for result in outcomes) == [200, 201]
    assert outcomes[0].json()["id"] == outcomes[1].json()["id"]
    assert scalar(app_engine, "SELECT count(*) FROM loans") == 1
    assert scalar(app_engine, "SELECT count(*) FROM idempotency_records") == 1
