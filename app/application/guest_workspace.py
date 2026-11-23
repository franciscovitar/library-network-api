"""Durable isolated synthetic library for an anonymous recruiter session.

The guest subject is a server-signed opaque UUID, never a browser-chosen branch or role.
All editable records belong to workspace-owned branches and members. The same
existing PostgreSQL loan transactions and locking implement guest circulation.
No cleanup, rate-limit or public deployment is provided by this module.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.persistence.models import (
    Book,
    Branch,
    Copy,
    DemoWorkspace,
    DemoWorkspaceBranch,
    DemoWorkspaceMember,
    IdempotencyRecord,
    Loan,
    Member,
)

WORKSPACE_TTL = timedelta(hours=24)
MAX_GUEST_LOANS = 25
SYNTHETIC_BOOKS = (
    ("Atlas de jardines imposibles", "A. Ejemplo"),
    ("El archivo de las mareas", "B. Ficción"),
    ("Inventario de lugares imaginarios", "C. Sintético"),
)


def valid_guest_subject(subject: str) -> bool:
    """Only signed guest UUID v4 identities may initialize disposable workspaces."""
    if not subject.startswith("guest:"):
        return False
    value = subject.removeprefix("guest:")
    try:
        uid = UUID(value)
        return uid.version == 4 and str(uid) == value
    except (ValueError, AttributeError):
        return False


def _guest_denied() -> HTTPException:
    return HTTPException(status_code=403, detail="Guest workspace access denied")


def guest_workspace(
    session: Session, subject: str, now: datetime, *, lock: bool = False
) -> DemoWorkspace:
    if not valid_guest_subject(subject):
        raise _guest_denied()
    statement = select(DemoWorkspace).where(DemoWorkspace.subject == subject)
    if lock:
        statement = statement.with_for_update()
    workspace = session.scalar(statement)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Guest workspace not initialized")
    if not workspace.active or workspace.expires_at <= now:
        raise HTTPException(status_code=410, detail="Guest workspace expired")
    return workspace


def owned_branch(session: Session, workspace: DemoWorkspace, branch_id: int) -> Branch:
    branch = session.scalar(
        select(Branch)
        .join(DemoWorkspaceBranch, DemoWorkspaceBranch.branch_id == Branch.id)
        .where(
            DemoWorkspaceBranch.workspace_id == workspace.id,
            Branch.id == branch_id,
            Branch.active.is_(True),
        )
    )
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    return branch


def owned_member(session: Session, workspace: DemoWorkspace, member_id: int) -> Member:
    member = session.scalar(
        select(Member)
        .join(DemoWorkspaceMember, DemoWorkspaceMember.member_id == Member.id)
        .where(
            DemoWorkspaceMember.workspace_id == workspace.id,
            Member.id == member_id,
        )
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


def owned_copy(session: Session, branch_id: int, copy_id: int) -> Copy:
    copy = session.scalar(
        select(Copy).where(
            Copy.id == copy_id,
            Copy.current_branch_id == branch_id,
            Copy.owning_branch_id == branch_id,
        )
    )
    if copy is None:
        raise HTTPException(status_code=404, detail="Copy not found")
    return copy


def owned_loan(
    session: Session, workspace: DemoWorkspace, loan_id: int
) -> Loan:
    loan = session.scalar(
        select(Loan)
        .join(DemoWorkspaceBranch, DemoWorkspaceBranch.branch_id == Loan.destination_branch_id)
        .where(DemoWorkspaceBranch.workspace_id == workspace.id, Loan.id == loan_id)
    )
    if loan is None:
        raise HTTPException(status_code=404, detail="Loan not found")
    return loan


def workspace_branch_ids(session: Session, workspace: DemoWorkspace) -> list[int]:
    return list(
        session.scalars(
            select(DemoWorkspaceBranch.branch_id)
            .where(DemoWorkspaceBranch.workspace_id == workspace.id)
            .order_by(DemoWorkspaceBranch.branch_id)
        )
    )


def start_guest_workspace(
    session: Session, *, subject: str, now: datetime
) -> tuple[DemoWorkspace, bool]:
    """Serialize concurrent guest starts; seed isolated real PostgreSQL rows once."""
    if not valid_guest_subject(subject):
        raise _guest_denied()
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:subject, 20261123))"),
        {"subject": subject},
    )
    workspace = session.scalar(
        select(DemoWorkspace).where(DemoWorkspace.subject == subject)
    )
    if workspace is not None:
        if workspace.expires_at <= now or not workspace.active:
            raise HTTPException(status_code=410, detail="Guest workspace expired")
        return workspace, False

    workspace = DemoWorkspace(
        subject=subject, created_at=now, expires_at=now + WORKSPACE_TTL, active=True
    )
    session.add(workspace)
    session.flush()

    digest = sha256(subject.encode("utf-8")).hexdigest()
    branches = [
        Branch(name=f"Demo {digest[:12]} · Central", active=True),
        Branch(name=f"Demo {digest[:12]} · Norte", active=True),
    ]
    session.add_all(branches)
    session.flush()
    session.add_all(
        DemoWorkspaceBranch(workspace_id=workspace.id, branch_id=branch.id)
        for branch in branches
    )

    members = [
        Member(code=f"D-{digest[:20]}-M{i:02d}", enabled=True)
        for i in range(1, 4)
    ]
    session.add_all(members)
    session.flush()
    session.add_all(
        DemoWorkspaceMember(workspace_id=workspace.id, member_id=member.id)
        for member in members
    )

    books = [
        Book(
            isbn=f"D-{sha256(f'{subject}/book/{i}'.encode()).hexdigest()[:18]}",
            title=title,
            author=author,
        )
        for i, (title, author) in enumerate(SYNTHETIC_BOOKS, start=1)
    ]
    session.add_all(books)
    session.flush()

    copies = [
        Copy(
            code=f"D-{digest[:20]}-C{i:02d}",
            book_id=books[(i - 1) % len(books)].id,
            owning_branch_id=branches[(i - 1) // 3].id,
            current_branch_id=branches[(i - 1) // 3].id,
            status="AVAILABLE",
            physical_condition="GOOD",
        )
        for i in range(1, 7)
    ]
    session.add_all(copies)
    session.flush()
    return workspace, True


def ensure_guest_loan_quota(
    session: Session,
    *,
    workspace: DemoWorkspace,
    scoped_key: str,
) -> None:
    """Allow exact idempotent retries while bounding new guest loan creation."""
    previous = session.scalar(
        select(IdempotencyRecord.id).where(
            IdempotencyRecord.operation == "LOCAL_REQUEST",
            IdempotencyRecord.key == scoped_key,
        )
    )
    if previous is not None:
        return
    branches = workspace_branch_ids(session, workspace)
    created_count = session.scalar(
        select(func.count())
        .select_from(Loan)
        .where(Loan.destination_branch_id.in_(branches))
    ) or 0
    if created_count >= MAX_GUEST_LOANS:
        raise HTTPException(status_code=429, detail="Workspace lending limit reached")
