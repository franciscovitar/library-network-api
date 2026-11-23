"""Expired synthetic guest cleanup on real PostgreSQL: exact preservation checks."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.application.guest_cleanup import (
    WorkspaceCleanupBlocked,
    cleanup_expired_workspaces,
)
from app.main import app
from app.persistence.models import StaffBranchGrant, StaffUser
from app.security import verified_subject
from tests.integration.helpers import scalar

pytestmark = pytest.mark.integration
GUEST = "/api/v2/guest"


def start(api, subject):
    app.dependency_overrides[verified_subject] = lambda: subject
    response = api.post(f"{GUEST}/start")
    assert response.status_code == 201, response.text
    return response.json()


def expire(engine, subject):
    with Session(engine) as session, session.begin():
        session.execute(
            text("UPDATE demo_workspaces SET expires_at=:when WHERE subject=:subject"),
            {"when": datetime.now(UTC) - timedelta(hours=2), "subject": subject},
        )


def test_cleanup_dry_run_and_apply_preserves_others(api, app_engine):
    old = f"guest:{uuid4()}"
    active = f"guest:{uuid4()}"
    old_info = start(api, old)
    active_info = start(api, active)
    old_branch = old_info["branches"][0]["branch_id"]
    active_branch = active_info["branches"][0]["branch_id"]
    m = api.get(f"{GUEST}/members").json()
    copies = api.get(f"{GUEST}/branches/{active_branch}/copies").json()["items"]
    assert len(m) == 3 and len(copies) == 3

    app.dependency_overrides[verified_subject] = lambda: old
    old_member = api.get(f"{GUEST}/members").json()[0]["id"]
    old_copy = api.get(f"{GUEST}/branches/{old_branch}/copies").json()["items"][0]["id"]
    issued = api.post(
        f"{GUEST}/loans/local",
        json={"branch_id": old_branch, "member_id": old_member, "copy_id": old_copy},
        headers={"Idempotency-Key": "cleanup-transaction"},
    )
    assert issued.status_code == 201, issued.text
    assert scalar(app_engine, "SELECT count(*) FROM loans") == 1

    expire(app_engine, old)
    with Session(app_engine) as session, session.begin():
        inspected = cleanup_expired_workspaces(session, now=datetime.now(UTC), apply=False)
    assert len(inspected) == 1
    assert inspected[0]["branches"] == 2
    assert inspected[0]["loans"] == 1
    assert scalar(app_engine, "SELECT count(*) FROM demo_workspaces") == 2
    assert scalar(app_engine, "SELECT count(*) FROM loans") == 1

    with Session(app_engine) as session, session.begin():
        removed = cleanup_expired_workspaces(session, now=datetime.now(UTC), apply=True)
    assert removed == inspected
    assert scalar(app_engine, "SELECT count(*) FROM demo_workspaces") == 1
    assert scalar(app_engine, "SELECT count(*) FROM demo_workspace_branches") == 2
    assert scalar(app_engine, "SELECT count(*) FROM demo_workspace_members") == 3
    assert scalar(app_engine, "SELECT count(*) FROM loans") == 0
    assert scalar(app_engine, "SELECT count(*) FROM idempotency_records") == 0
    assert scalar(app_engine, "SELECT count(*) FROM copies") == 16
    assert scalar(app_engine, "SELECT count(*) FROM books") == 8
    assert scalar(app_engine, "SELECT count(*) FROM members") == 9
    assert scalar(app_engine, "SELECT count(*) FROM branches") == 5
    with Session(app_engine) as session, session.begin():
        assert cleanup_expired_workspaces(session, now=datetime.now(UTC), apply=True) == []
    app.dependency_overrides[verified_subject] = lambda: active
    assert api.get(f"{GUEST}/branches/{active_branch}/overview").status_code == 200


def test_cleanup_rejects_guest_branch_with_staff_grant(api, app_engine):
    subject = f"guest:{uuid4()}"
    info = start(api, subject)
    branch = info["branches"][0]["branch_id"]
    expire(app_engine, subject)
    with Session(app_engine) as session, session.begin():
        staff = StaffUser(subject="cleanup-test-staff", active=True)
        session.add(staff)
        session.flush()
        session.add(
            StaffBranchGrant(
                staff_user_id=staff.id,
                branch_id=branch,
                role="VIEWER",
                active=True,
            )
        )
    with pytest.raises(WorkspaceCleanupBlocked):
        with Session(app_engine) as session, session.begin():
            cleanup_expired_workspaces(session, now=datetime.now(UTC), apply=True)
    assert scalar(app_engine, "SELECT count(*) FROM demo_workspaces") == 1
    assert scalar(app_engine, "SELECT count(*) FROM staff_branch_grants") == 1
    assert scalar(app_engine, "SELECT count(*) FROM copies") == 16


def test_cleanup_rejects_invalid_input_without_mutating(api, app_engine):
    subject = f"guest:{uuid4()}"
    start(api, subject)
    expire(app_engine, subject)
    with pytest.raises(ValueError):
        with Session(app_engine) as session, session.begin():
            cleanup_expired_workspaces(session, now=datetime.now(UTC), limit=0, apply=True)
    with pytest.raises(ValueError):
        with Session(app_engine) as session, session.begin():
            cleanup_expired_workspaces(session, now=datetime(2026, 11, 23), apply=True)
    assert scalar(app_engine, "SELECT count(*) FROM demo_workspaces") == 1
