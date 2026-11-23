"""Branch-local circulation reusing the existing PostgreSQL locking/idempotency engine.

These commands remain LOCAL-ONLY until authentication and branch-scoped authorization
are built and proved. A local loan must never generate an interbranch transfer.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.application.locks import copy_id_of_loan, lock_copy, lock_loan
from app.application.request_loan import _claim_idempotency_key
from app.domain.errors import ConflictError, NotFoundError
from app.domain.rules import LOAN_PERIOD, canonical_request_hash
from app.domain.states import CopyStatus, IdempotentOperation, LoanKind, LoanStatus, PhysicalCondition
from app.persistence.models import Branch, IdempotencyRecord, Loan, Member

OPERATION = IdempotentOperation.LOCAL_REQUEST


def create_local_loan(
    session: Session,
    *,
    member_id: int,
    copy_id: int,
    branch_id: int,
    idempotency_key: str,
    now: datetime,
) -> tuple[Loan, bool]:
    """Atomically claim the request, lock the physical copy, then issue the loan."""
    request_hash = canonical_request_hash(
        OPERATION.value,
        {"member_id": member_id, "copy_id": copy_id, "branch_id": branch_id},
    )
    loan_id = session.execute(
        text("SELECT nextval(pg_get_serial_sequence('loans', 'id'))")
    ).scalar_one()
    claimed = _claim_idempotency_key(
        session, idempotency_key, request_hash, loan_id, now, operation=OPERATION
    )
    if not claimed:
        existing = session.scalars(
            select(IdempotencyRecord).where(
                IdempotencyRecord.operation == OPERATION.value,
                IdempotencyRecord.key == idempotency_key,
            )
        ).one()
        if existing.request_hash != request_hash:
            raise ConflictError(
                "idempotency_key_reuse",
                "This Idempotency-Key was already used with a different request body.",
            )
        return session.get(Loan, existing.resource_id), False

    copy = lock_copy(session, copy_id)
    member = session.get(Member, member_id)
    branch = session.get(Branch, branch_id)
    if member is None:
        raise NotFoundError("member_not_found", f"Member {member_id} does not exist.")
    if branch is None:
        raise NotFoundError("branch_not_found", f"Branch {branch_id} does not exist.")
    if not member.enabled:
        raise ConflictError("member_disabled", "Member is not enabled.")
    if not branch.active:
        raise ConflictError("branch_inactive", "Branch is inactive.")
    if copy.status != CopyStatus.AVAILABLE.value:
        raise ConflictError("copy_not_available", "Copy is not available.")
    if copy.current_branch_id != branch.id or copy.owning_branch_id != branch.id:
        raise ConflictError("copy_not_at_branch", "Copy is not available at this branch.")

    loan = Loan(
        id=loan_id,
        kind=LoanKind.LOCAL.value,
        member_id=member.id,
        copy_id=copy.id,
        origin_branch_id=branch.id,
        destination_branch_id=branch.id,
        status=LoanStatus.ACTIVE.value,
        requested_at=now,
        started_at=now,
        due_at=now + LOAN_PERIOD,
    )
    session.add(loan)
    copy.status = CopyStatus.ON_LOAN.value
    session.flush()
    return loan, True


def return_local_loan(
    session: Session,
    *,
    loan_id: int,
    branch_id: int,
    condition: PhysicalCondition,
    now: datetime,
) -> Loan:
    """Atomically close a local loan; damaged physical copies never become available."""
    copy = lock_copy(session, copy_id_of_loan(session, loan_id))
    loan = lock_loan(session, loan_id)
    if loan.kind != LoanKind.LOCAL.value:
        raise ConflictError("wrong_loan_kind", "Interlibrary loans require transfer-based return.")
    if loan.status != LoanStatus.ACTIVE.value:
        raise ConflictError("loan_not_active", "Loan is not active.")
    if loan.destination_branch_id != branch_id or copy.current_branch_id != branch_id:
        raise ConflictError("wrong_branch", "Return must be recorded at the issuing branch.")
    if copy.status != CopyStatus.ON_LOAN.value:
        raise ConflictError("copy_state_inconsistent", "Copy is not currently on loan.")
    loan.status = LoanStatus.CLOSED.value
    loan.borrower_returned_at = now
    loan.return_condition = condition.value
    loan.closed_at = now
    copy.physical_condition = condition.value
    copy.status = (
        CopyStatus.RETIRED.value
        if condition is PhysicalCondition.DAMAGED
        else CopyStatus.AVAILABLE.value
    )
    session.flush()
    return loan
