"""Small helpers shared by the API-level integration tests."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

API = "/api/v1"


def request_loan(api, key="demo-req-001", *, member=1, copy=1, dest=2):
    return api.post(
        f"{API}/loans/interlibrary",
        json={"member_id": member, "copy_id": copy, "destination_branch_id": dest},
        headers={"Idempotency-Key": key},
    )


def advance(api, transfer_id: int, status: str):
    return api.post(f"{API}/transfers/{transfer_id}/transitions", json={"next_status": status})


def advance_to_received(api, transfer_id: int) -> None:
    for status in ("DISPATCHED", "IN_TRANSIT", "RECEIVED"):
        response = advance(api, transfer_id, status)
        assert response.status_code == 200, response.text


def activate(api, loan_id: int):
    return api.post(f"{API}/loans/{loan_id}/activate")


def give_back(api, loan_id: int, condition="GOOD"):
    return api.post(f"{API}/loans/{loan_id}/return", json={"condition": condition})


def get_loan(api, loan_id: int) -> dict[str, Any]:
    response = api.get(f"{API}/loans/{loan_id}")
    assert response.status_code == 200, response.text
    return response.json()


def transfer_of(loan: dict[str, Any], direction: str) -> dict[str, Any]:
    return next(t for t in loan["transfers"] if t["direction"] == direction)


def make_active_loan(api, key="demo-req-001", **kw) -> dict[str, Any]:
    """Request, receive the outward transfer and activate. Returns the loan JSON."""
    created = request_loan(api, key, **kw)
    assert created.status_code == 201, created.text
    loan = created.json()
    advance_to_received(api, transfer_of(loan, "OUTBOUND")["id"])
    activated = activate(api, loan["id"])
    assert activated.status_code == 200, activated.text
    return activated.json()


def sql(engine: Engine, query: str, **params) -> list[tuple]:
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(query), params)]


def scalar(engine: Engine, query: str, **params):
    return sql(engine, query, **params)[0][0]


def counts(engine: Engine) -> dict[str, int]:
    return {
        table: scalar(engine, f"SELECT count(*) FROM {table}")
        for table in ("loans", "transfers", "transfer_events", "idempotency_records")
    }


def event_path(engine: Engine, transfer_id: int) -> list[str]:
    rows = sql(
        engine,
        "SELECT to_status FROM transfer_events WHERE transfer_id = :t ORDER BY id",
        t=transfer_id,
    )
    return [r[0] for r in rows]
