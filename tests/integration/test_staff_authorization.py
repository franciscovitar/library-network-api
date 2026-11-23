"""Branch authorization through actual PostgreSQL rows and FastAPI contracts."""

import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.main import app
from app.persistence.models import Branch, StaffBranchGrant, StaffUser
from app.security import verified_subject
from tests.integration.helpers import API, scalar

pytestmark = pytest.mark.integration
SECURE = "/api/v2"


def provision(engine, subject, *, branch=1, role="LIBRARIAN", active=True):
    with Session(engine) as session, session.begin():
        user = StaffUser(subject=subject, active=active)
        session.add(user)
        session.flush()
        session.add(
            StaffBranchGrant(staff_user_id=user.id, branch_id=branch, role=role, active=True)
        )


def as_staff(subject):
    app.dependency_overrides[verified_subject] = lambda: subject


def issue(api, *, branch=1, copy=1, member=1, key="staff-checkout"):
    return api.post(
        f"{SECURE}/loans/local",
        json={"member_id": member, "copy_id": copy, "branch_id": branch},
        headers={"Idempotency-Key": key},
    )


def checkin(api, loan_id, *, branch=1):
    return api.post(
        f"{SECURE}/loans/{loan_id}/local-return",
        json={"branch_id": branch, "condition": "GOOD"},
    )


def test_default_anonymous_is_denied_and_legacy_requires_opt_in(api, monkeypatch):
    assert api.get(f"{SECURE}/me").status_code == 401
    assert api.get(f"{SECURE}/catalog/search", params={"branch_id": 1}).status_code == 401
    assert issue(api).status_code == 401

    monkeypatch.delenv("LIBRARY_ENABLE_UNSAFE_V1", raising=False)
    assert api.get(f"{API}/branches").status_code == 404
    assert (
        api.post(
            f"{API}/loans/local",
            json={"member_id": 1, "copy_id": 1, "branch_id": 1},
            headers={"Idempotency-Key": "legacy-blocked"},
        ).status_code
        == 404
    )


def test_managed_host_vetoes_legacy_even_if_opted_in(api, monkeypatch):
    monkeypatch.setenv("LIBRARY_RUNTIME_MODE", "local")
    monkeypatch.setenv("LIBRARY_ENABLE_UNSAFE_V1", "1")
    monkeypatch.setenv("VERCEL", "1")
    assert api.get(f"{API}/branches").status_code == 404


def test_active_librarian_can_search_issue_read_and_return(api, app_engine):
    provision(app_engine, "alice")
    as_staff("alice")
    profile = api.get(f"{SECURE}/me")
    assert profile.status_code == 200
    assert profile.json()["branches"] == [
        {"branch_id": 1, "branch_name": "Central Branch", "role": "LIBRARIAN"}
    ]
    found = api.get(f"{SECURE}/catalog/search", params={"branch_id": 1, "q": "synthetic"})
    assert found.status_code == 200
    assert found.json()["items"][0]["available_copies"] == 1
    created = issue(api)
    assert created.status_code == 201, created.text
    loan = created.json()
    assert loan["status"] == "ACTIVE"
    assert api.get(f"{SECURE}/loans/{loan['id']}").status_code == 200
    after = api.get(f"{SECURE}/catalog/search", params={"branch_id": 1, "q": "synthetic"})
    assert after.json()["items"][0]["available_copies"] == 0
    assert checkin(api, loan["id"]).status_code == 200
    assert scalar(app_engine, "SELECT status FROM copies WHERE id = 1") == "AVAILABLE"


def test_viewer_can_read_but_cannot_checkout(api, app_engine):
    provision(app_engine, "viewer", role="VIEWER")
    as_staff("viewer")
    assert api.get(f"{SECURE}/catalog/search", params={"branch_id": 1}).status_code == 200
    denied = issue(api)
    assert denied.status_code == 403
    assert scalar(app_engine, "SELECT count(*) FROM loans") == 0


def test_unprovisioned_user_cannot_read_or_write(api, app_engine):
    as_staff("unknown")
    assert api.get(f"{SECURE}/me").json()["branches"] == []
    assert api.get(f"{SECURE}/catalog/search", params={"branch_id": 1}).status_code == 403
    assert issue(api).status_code == 403
    assert scalar(app_engine, "SELECT count(*) FROM loans") == 0


def test_cross_branch_read_and_return_never_exposes_loan(api, app_engine):
    provision(app_engine, "alice", branch=1)
    provision(app_engine, "bob", branch=2)
    as_staff("alice")
    loan = issue(api).json()
    as_staff("bob")
    assert api.get(f"{SECURE}/catalog/search", params={"branch_id": 1}).status_code == 403
    assert issue(api, branch=1, key="cross-issue").status_code == 403
    assert api.get(f"{SECURE}/loans/{loan['id']}").status_code == 404
    assert checkin(api, loan["id"], branch=2).status_code == 404
    assert scalar(app_engine, "SELECT status FROM copies WHERE id = 1") == "ON_LOAN"
    as_staff("alice")
    assert checkin(api, loan["id"]).status_code == 200


def test_revoking_staff_or_grant_takes_effect_without_new_token(api, app_engine):
    provision(app_engine, "alice")
    as_staff("alice")
    assert api.get(f"{SECURE}/catalog/search", params={"branch_id": 1}).status_code == 200
    with Session(app_engine) as session, session.begin():
        session.execute(update(StaffBranchGrant).values(active=False))
    assert api.get(f"{SECURE}/catalog/search", params={"branch_id": 1}).status_code == 403
    with Session(app_engine) as session, session.begin():
        session.execute(update(StaffBranchGrant).values(active=True))
        session.execute(update(StaffUser).values(active=False))
    assert issue(api).status_code == 403
    assert scalar(app_engine, "SELECT count(*) FROM loans") == 0


def test_inactive_branch_and_admin_without_explicit_grant_are_denied(api, app_engine):
    provision(app_engine, "network-admin", role="NETWORK_ADMIN", branch=1)
    as_staff("network-admin")
    assert api.get(f"{SECURE}/catalog/search", params={"branch_id": 2}).status_code == 403
    assert issue(api, branch=2, key="no-admin-bypass").status_code == 403
    with Session(app_engine) as session, session.begin():
        session.execute(update(Branch).where(Branch.id == 1).values(active=False))
    assert api.get(f"{SECURE}/catalog/search", params={"branch_id": 1}).status_code == 403


def test_idempotency_key_is_scoped_to_user_and_branch(api, app_engine):
    provision(app_engine, "alice", branch=1)
    provision(app_engine, "bob", branch=1)
    as_staff("alice")
    first = issue(api, key="same-client-key", copy=1)
    assert first.status_code == 201
    as_staff("bob")
    second = issue(api, key="same-client-key", copy=3, member=2)
    assert second.status_code == 201, second.text
    assert first.json()["id"] != second.json()["id"]
    assert scalar(app_engine, "SELECT count(*) FROM loans") == 2
    assert scalar(app_engine, "SELECT count(*) FROM idempotency_records") == 2


def test_signed_bearer_token_reaches_real_database_and_cannot_escalate(
    api, app_engine, monkeypatch
):
    """No mocked identity: signed RS256 -> FastAPI auth -> PostgreSQL branch authorization."""
    provision(app_engine, "signed-staff", branch=1)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    jwk["kid"] = "signed-integration-ci"
    monkeypatch.setenv("LIBRARY_JWKS_JSON", json.dumps({"keys": [jwk]}))
    monkeypatch.setenv("LIBRARY_JWT_ISSUER", "https://auth.example.test")
    monkeypatch.setenv("LIBRARY_JWT_AUDIENCE", "library-network-api")
    now = datetime.now(UTC)
    claims = {
        "sub": "signed-staff",
        "iss": "https://auth.example.test",
        "aud": "library-network-api",
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=3)).timestamp()),
    }
    token = jwt.encode(claims, private, algorithm="RS256", headers={"kid": jwk["kid"]})
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "signed-flow-1"}
    assert api.get(f"{SECURE}/me", headers=headers).json()["branches"][0]["branch_id"] == 1
    assert (
        api.get(f"{SECURE}/catalog/search", params={"branch_id": 1}, headers=headers).status_code
        == 200
    )

    denied = api.post(
        f"{SECURE}/loans/local",
        json={"member_id": 1, "copy_id": 2, "branch_id": 2},
        headers=headers | {"X-Role": "NETWORK_ADMIN"},
    )
    assert denied.status_code == 403
    assert scalar(app_engine, "SELECT count(*) FROM loans") == 0

    issued = api.post(
        f"{SECURE}/loans/local",
        json={"member_id": 1, "copy_id": 1, "branch_id": 1},
        headers=headers,
    )
    assert issued.status_code == 201, issued.text
    assert issued.json()["status"] == "ACTIVE"
    assert scalar(app_engine, "SELECT status FROM copies WHERE id=1") == "ON_LOAN"
    returned = api.post(
        f"{SECURE}/loans/{issued.json()['id']}/local-return",
        json={"branch_id": 1, "condition": "GOOD"},
        headers=headers,
    )
    assert returned.status_code == 200
    assert scalar(app_engine, "SELECT status FROM copies WHERE id=1") == "AVAILABLE"

    wrong_audience = jwt.encode(
        claims | {"aud": "different-audience"},
        private,
        algorithm="RS256",
        headers={"kid": jwk["kid"]},
    )
    assert (
        api.get(f"{SECURE}/me", headers={"Authorization": f"Bearer {wrong_audience}"}).status_code
        == 401
    )


def test_operational_overview_is_real_and_scoped(api, app_engine):
    provision(app_engine, "operator", branch=1)
    as_staff("operator")
    url = f"{SECURE}/branches/1/overview"
    baseline = api.get(url)
    assert baseline.status_code == 200, baseline.text
    row = baseline.json()
    assert row["branch_id"] == 1
    assert (row["total_copies"], row["available_copies"], row["catalog_titles"]) == (4, 3, 4)
    assert row["active_loans"] == 0
    assert row["pending_dispatches"] == 0
    assert api.get(f"{SECURE}/branches/2/overview").status_code == 403

    loan = issue(api, key="overview-local-1")
    assert loan.status_code == 201
    during = api.get(url).json()
    assert during["available_copies"] == 2
    assert during["active_loans"] == 1
    assert during["total_copies"] == 4

    assert checkin(api, loan.json()["id"]).status_code == 200
    restored = api.get(url).json()
    assert (restored["available_copies"], restored["active_loans"]) == (3, 0)

    transfer = api.post(
        f"{API}/loans/interlibrary",
        json={"member_id": 2, "copy_id": 3, "destination_branch_id": 2},
        headers={"Idempotency-Key": "overview-transfer-1"},
    )
    assert transfer.status_code == 201
    assert api.get(url).json()["pending_dispatches"] == 1


def test_overview_viewer_can_read_and_revoked_grant_cannot(api, app_engine):
    provision(app_engine, "viewer", branch=1, role="VIEWER")
    as_staff("viewer")
    url = f"{SECURE}/branches/1/overview"
    assert api.get(url).status_code == 200
    assert issue(api).status_code == 403
    with Session(app_engine) as session, session.begin():
        session.execute(update(StaffBranchGrant).values(active=False))
    assert api.get(url).status_code == 403


def test_staff_can_select_real_branch_copy_and_exact_synthetic_member(api, app_engine):
    provision(app_engine, "staff", branch=1, role="LIBRARIAN")
    as_staff("staff")
    copies_url = f"{SECURE}/branches/1/copies"
    members_url = f"{SECURE}/branches/1/members/lookup"
    first = api.get(copies_url)
    assert first.status_code == 200, first.text
    assert first.json()["total"] == 4
    assert first.json()["items"][0]["title"]
    assert {copy["id"] for copy in first.json()["items"]} == {1, 3, 7, 10}
    assert api.get(copies_url, params={"q": "synthetic"}).json()["total"] == 1
    assert api.get(copies_url, params={"q": "%"}).json()["items"] == []
    assert api.get(copies_url, params={"limit": 0}).status_code == 422

    member = api.get(members_url, params={"code": "M0001"})
    assert member.status_code == 200
    assert member.json() == {"id": 1, "code": "M0001", "enabled": True}
    disabled = api.get(members_url, params={"code": "M0006"})
    assert disabled.json()["enabled"] is False
    assert api.get(members_url, params={"code": "nobody"}).status_code == 404
    assert api.get(f"{SECURE}/branches/2/copies").status_code == 403
    assert api.get(
        f"{SECURE}/branches/2/members/lookup", params={"code": "M0001"}
    ).status_code == 403

    loan = issue(api, key="copy-finder-test")
    assert loan.status_code == 201
    after = api.get(copies_url, params={"q": "CP-0001"}).json()["items"][0]
    assert after["status"] == "ON_LOAN"
    assert checkin(api, loan.json()["id"]).status_code == 200
    restored = api.get(copies_url, params={"q": "CP-0001"}).json()["items"][0]
    assert restored["status"] == "AVAILABLE"
