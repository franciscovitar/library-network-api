"""Guest workspaces: actual PostgreSQL isolation, replay and negative API tests."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.application import guest_workspace as guest_module
from app.main import app
from app.security import verified_subject
from tests.integration.helpers import scalar

pytestmark = pytest.mark.integration
BASE = "/api/v2/guest"


def as_guest(subject):
    app.dependency_overrides[verified_subject] = lambda: subject


def guest_id():
    return f"guest:{uuid4()}"


def start(api, subject):
    as_guest(subject)
    return api.post(f"{BASE}/start")


def profile(api, subject):
    as_guest(subject)
    return api.get(f"{BASE}/me").json()


def guest_issue(api, subject, branch, member, copy, key):
    as_guest(subject)
    return api.post(
        f"{BASE}/loans/local",
        json={"branch_id": branch, "member_id": member, "copy_id": copy},
        headers={"Idempotency-Key": key},
    )


def test_two_guests_are_real_isolated_workspaces(api, app_engine):
    a, b = guest_id(), guest_id()
    first = start(api, a)
    assert first.status_code == 201, first.text
    replay = start(api, a)
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    second = start(api, b)
    assert second.status_code == 201, second.text

    a_profile, b_profile = first.json(), second.json()
    a_branches = [x["branch_id"] for x in a_profile["branches"]]
    b_branches = [x["branch_id"] for x in b_profile["branches"]]
    assert len(a_branches) == len(b_branches) == 2
    assert set(a_branches).isdisjoint(b_branches)
    assert scalar(app_engine, "SELECT count(*) FROM demo_workspaces") == 2
    assert scalar(app_engine, "SELECT count(*) FROM demo_workspace_branches") == 4
    assert scalar(app_engine, "SELECT count(*) FROM demo_workspace_members") == 6

    as_guest(a)
    a_members = api.get(f"{BASE}/members").json()
    a_copies = api.get(f"{BASE}/branches/{a_branches[0]}/copies").json()["items"]
    a_catalog = api.get(f"{BASE}/branches/{a_branches[0]}/catalog").json()
    assert len(a_members) == 3
    assert len(a_copies) == 3
    assert a_catalog["total"] == 3
    assert a_catalog["items"][0]["title"]
    assert api.get(f"{BASE}/branches/{b_branches[0]}/overview").status_code == 404
    assert api.get(f"{BASE}/branches/{b_branches[0]}/catalog").status_code == 404
    assert api.get(f"{BASE}/branches/{b_branches[0]}/copies").status_code == 404

    as_guest(b)
    b_members = api.get(f"{BASE}/members").json()
    b_copies = api.get(f"{BASE}/branches/{b_branches[0]}/copies").json()["items"]
    assert {m["id"] for m in a_members}.isdisjoint(m["id"] for m in b_members)
    assert {c["id"] for c in a_copies}.isdisjoint(c["id"] for c in b_copies)

    issued = guest_issue(
        api, a, a_branches[0], a_members[0]["id"], a_copies[0]["id"], "test-1"
    )
    assert issued.status_code == 201, issued.text
    loan_id = issued.json()["id"]
    as_guest(b)
    assert api.get(f"{BASE}/loans/{loan_id}").status_code == 404
    assert api.post(
        f"{BASE}/loans/{loan_id}/local-return",
        json={"branch_id": b_branches[0], "condition": "GOOD"},
    ).status_code == 404

    as_guest(a)
    during = api.get(f"{BASE}/branches/{a_branches[0]}/overview").json()
    assert during["active_loans"] == 1
    assert during["available_copies"] == 2
    reread = guest_issue(
        api, a, a_branches[0], a_members[0]["id"], a_copies[0]["id"], "test-1"
    )
    assert reread.status_code == 200
    assert reread.json()["id"] == loan_id
    changed = guest_issue(
        api, a, a_branches[0], a_members[1]["id"], a_copies[0]["id"], "test-1"
    )
    assert changed.status_code == 409

    as_guest(b)
    assert api.get(f"{BASE}/branches/{b_branches[0]}/overview").json()["active_loans"] == 0
    as_guest(a)
    returned = api.post(
        f"{BASE}/loans/{loan_id}/local-return",
        json={"branch_id": a_branches[0], "condition": "GOOD"},
    )
    assert returned.status_code == 200, returned.text
    assert api.get(f"{BASE}/branches/{a_branches[0]}/overview").json()["available_copies"] == 3


def test_foreign_branch_copy_and_member_cannot_mutate(api, app_engine):
    a, b = guest_id(), guest_id()
    ap, bp = start(api, a).json(), start(api, b).json()
    a_branch = ap["branches"][0]["branch_id"]
    b_branch = bp["branches"][0]["branch_id"]
    as_guest(a)
    member = api.get(f"{BASE}/members").json()[0]["id"]
    own_copy = api.get(f"{BASE}/branches/{a_branch}/copies").json()["items"][0]["id"]
    as_guest(b)
    foreign_member = api.get(f"{BASE}/members").json()[0]["id"]
    foreign_copy = api.get(f"{BASE}/branches/{b_branch}/copies").json()["items"][0]["id"]

    for branch, mid, cid in [
        (b_branch, member, own_copy),
        (a_branch, foreign_member, own_copy),
        (a_branch, member, foreign_copy),
    ]:
        denied = guest_issue(api, a, branch, mid, cid, f"foreign-{branch}-{mid}-{cid}")
        assert denied.status_code == 404, denied.text
    assert scalar(app_engine, "SELECT count(*) FROM loans") == 0
    assert scalar(app_engine, "SELECT count(*) FROM idempotency_records") == 0


def test_expiry_and_staff_subject_fail_closed(api, app_engine):
    subject = guest_id()
    assert start(api, "github:12345").status_code == 403
    as_guest(subject)
    assert api.get(f"{BASE}/me").status_code == 404
    assert start(api, subject).status_code == 201
    with Session(app_engine) as session, session.begin():
        session.execute(
            text("UPDATE demo_workspaces SET expires_at=:end WHERE subject=:subject"),
            {"end": datetime.now(UTC) - timedelta(hours=1), "subject": subject},
        )
    assert api.get(f"{BASE}/me").status_code == 410
    assert api.post(f"{BASE}/start").status_code == 410
    assert api.get(f"{BASE}/members").status_code == 410
    assert api.get("/api/v2/me").json()["branches"] == []


def test_guest_new_loan_quota_preserves_exact_replay(api, app_engine, monkeypatch):
    monkeypatch.setattr(guest_module, "MAX_GUEST_LOANS", 1)
    subject = guest_id()
    branch = start(api, subject).json()["branches"][0]["branch_id"]
    as_guest(subject)
    members = api.get(f"{BASE}/members").json()
    copies = api.get(f"{BASE}/branches/{branch}/copies").json()["items"]
    first = guest_issue(
        api, subject, branch, members[0]["id"], copies[0]["id"], "quota-one"
    )
    assert first.status_code == 201, first.text
    replay = guest_issue(
        api, subject, branch, members[0]["id"], copies[0]["id"], "quota-one"
    )
    assert replay.status_code == 200
    other = guest_issue(
        api, subject, branch, members[1]["id"], copies[1]["id"], "quota-two"
    )
    assert other.status_code == 429
    assert scalar(app_engine, "SELECT count(*) FROM loans") == 1
