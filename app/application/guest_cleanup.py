"""Conservative, transactional cleanup for expired synthetic guest workspaces.

Read-only preview by default. Never run against a real database without approval.
One workspace's related rows are deleted together, or the transaction rolls back.
Foreign/copied institutional data block cleanup rather than being removed.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.persistence.models import (
    Book,
    Branch,
    Copy,
    DemoCreationWindow,
    DemoWorkspace,
    DemoWorkspaceBranch,
    DemoWorkspaceMember,
    IdempotencyRecord,
    Loan,
    Member,
    StaffBranchGrant,
    Transfer,
    TransferEvent,
)

MAX_BATCH = 25


class WorkspaceCleanupBlocked(RuntimeError):
    """Prevent deletion whenever a workspace has unexpected external references."""


def _ids(session: Session, statement) -> list[int]:
    return list(session.scalars(statement))


def _guard_workspace(
    session: Session,
    workspace: DemoWorkspace,
) -> tuple[list[int], list[int], list[int], list[int], list[int], list[int]]:
    branches = _ids(
        session,
        select(DemoWorkspaceBranch.branch_id).where(
            DemoWorkspaceBranch.workspace_id == workspace.id
        ),
    )
    members = _ids(
        session,
        select(DemoWorkspaceMember.member_id).where(
            DemoWorkspaceMember.workspace_id == workspace.id
        ),
    )
    if not branches or not members:
        raise WorkspaceCleanupBlocked("Workspace membership is unexpectedly incomplete")

    copies = list(
        session.scalars(select(Copy).where(Copy.owning_branch_id.in_(branches)))
    )
    copy_ids = [item.id for item in copies]
    book_ids = list({item.book_id for item in copies})
    if any(item.current_branch_id not in branches for item in copies):
        raise WorkspaceCleanupBlocked("Owned copy is located outside its workspace")

    outside_copy = session.scalar(
        select(Copy.id).where(
            or_(
                Copy.current_branch_id.in_(branches),
                Copy.book_id.in_(book_ids),
            ),
            ~Copy.id.in_(copy_ids),
        ).limit(1)
    )
    if outside_copy is not None:
        raise WorkspaceCleanupBlocked("External copy references a guest branch or guest book")

    staff_grant = session.scalar(
        select(StaffBranchGrant.id)
        .where(StaffBranchGrant.branch_id.in_(branches))
        .limit(1)
    )
    if staff_grant is not None:
        raise WorkspaceCleanupBlocked("Staff access exists on guest branch")

    loans = list(
        session.scalars(
            select(Loan).where(
                or_(
                    Loan.copy_id.in_(copy_ids),
                    Loan.member_id.in_(members),
                    Loan.origin_branch_id.in_(branches),
                    Loan.destination_branch_id.in_(branches),
                )
            )
        )
    )
    for loan in loans:
        if (
            loan.copy_id not in copy_ids
            or loan.member_id not in members
            or loan.origin_branch_id not in branches
            or loan.destination_branch_id not in branches
        ):
            raise WorkspaceCleanupBlocked("Loan references a resource outside its workspace")

    loan_ids = [item.id for item in loans]
    transfers = _ids(
        session,
        select(Transfer.id).where(Transfer.loan_id.in_(loan_ids)),
    )
    return branches, members, copy_ids, book_ids, loan_ids, transfers


def cleanup_expired_workspaces(
    session: Session,
    *,
    now: datetime,
    limit: int = 10,
    apply: bool = False,
) -> list[dict[str, int]]:
    """Inspect or delete up to 'limit' expired guests in the caller's transaction.

    The operator owns the transaction: commit/rollback happens outside this function.
    Never deletes unexpired workspaces, existing institutional seed or external rows.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if not 1 <= limit <= MAX_BATCH:
        raise ValueError(f"limit must be between 1 and {MAX_BATCH}")

    candidates = list(
        session.scalars(
            select(DemoWorkspace)
            .where(DemoWorkspace.expires_at <= now)
            .order_by(DemoWorkspace.expires_at, DemoWorkspace.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    results = []
    for workspace in candidates:
        branches, members, copies, books, loans, transfers = _guard_workspace(
            session, workspace
        )
        summary = {
            "workspace_id": workspace.id,
            "branches": len(branches),
            "members": len(members),
            "copies": len(copies),
            "books": len(books),
            "loans": len(loans),
            "transfers": len(transfers),
        }
        results.append(summary)
        if not apply:
            continue

        # Dependency order matters: no cascading deletes of unrelated rows.
        session.execute(
            delete(TransferEvent).where(TransferEvent.transfer_id.in_(transfers))
        )
        session.execute(delete(Transfer).where(Transfer.id.in_(transfers)))
        session.execute(
            delete(IdempotencyRecord).where(
                IdempotencyRecord.resource_id.in_(loans)
            )
        )
        session.execute(delete(Loan).where(Loan.id.in_(loans)))
        session.execute(delete(Copy).where(Copy.id.in_(copies)))
        session.execute(
            delete(DemoWorkspaceBranch).where(
                DemoWorkspaceBranch.workspace_id == workspace.id
            )
        )
        session.execute(
            delete(DemoWorkspaceMember).where(
                DemoWorkspaceMember.workspace_id == workspace.id
            )
        )
        session.execute(delete(Book).where(Book.id.in_(books)))
        session.execute(delete(Member).where(Member.id.in_(members)))
        session.execute(delete(Branch).where(Branch.id.in_(branches)))
        session.delete(workspace)

    if apply:
        # Retain hourly aggregate budget rows for 48 hours for investigation;
        # no raw IP addresses or persistent visitor identity logs are written.
        session.execute(
            delete(DemoCreationWindow).where(
                DemoCreationWindow.window_start < now - timedelta(hours=48)
            )
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely inspect/remove expired synthetic demos")
    parser.add_argument("--apply", action="store_true", help="Delete (off by default)")
    parser.add_argument("--limit", type=int, default=10)
    options = parser.parse_args()

    if options.apply and os.getenv("LIBRARY_DEMO_CLEANUP_ENABLED") != "1":
        parser.error("Refusing to mutate without LIBRARY_DEMO_CLEANUP_ENABLED=1")
    from app.db import get_engine

    with Session(get_engine()) as session, session.begin():
        summaries = cleanup_expired_workspaces(
            session,
            now=datetime.now(UTC),
            limit=options.limit,
            apply=options.apply,
        )
    print(
        json.dumps(
            {
                "mode": "APPLIED" if options.apply else "DRY_RUN",
                "workspaces": summaries,
                "count": len(summaries),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
