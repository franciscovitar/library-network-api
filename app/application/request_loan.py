"""Use case: request an interlibrary loan (creates the loan AND its outward transfer).

Order inside the single transaction (V1.1 contract):
  1. claim (operation, Idempotency-Key) with an atomic INSERT ... ON CONFLICT DO NOTHING;
  2. lock the copy row (SELECT ... FOR UPDATE);
  3. validate everything while the copy is locked;
  4. insert loan + outward PREPARED transfer + initial history, copy -> RESERVED.

The claim carries a pre-allocated loan id; the idempotency FK is deferred, so the claim can
never be committed without its loan. Any failure (validation, injected error, constraint)
rolls back the claim too: a rejected request leaves no idempotency record behind.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.application.locks import lock_copy
from app.domain.errors import ConflictError, NotFoundError
from app.domain.rules import canonical_request_hash
from app.domain.states import (
    CopyStatus,
    IdempotentOperation,
    LoanKind,
    LoanStatus,
    TransferDirection,
    TransferStatus,
)
from app.persistence.models import (
    Branch,
    IdempotencyRecord,
    Loan,
    Member,
    Transfer,
    TransferEvent,
)

OPERATION = IdempotentOperation.INTERLIBRARY_REQUEST


def _claim_idempotency_key(
    session: Session,
    key: str,
    request_hash: str,
    loan_id: int,
    now: datetime,
    operation: IdempotentOperation = OPERATION,
) -> bool:
    """True if this transaction won the key, False if it already exists (committed)."""
    claimed = session.execute(
        pg_insert(IdempotencyRecord.__table__)
        .values(
            operation=operation.value,
            key=key,
            request_hash=request_hash,
            resource_type="LOAN",
            resource_id=loan_id,
            created_at=now,
        )
        .on_conflict_do_nothing(index_elements=["operation", "key"])
        .returning(IdempotencyRecord.__table__.c.id)
    ).scalar_one_or_none()
    return claimed is not None


def _add_initial_history(session: Session, transfer: Transfer, now: datetime) -> None:
    session.add(
        TransferEvent(
            transfer_id=transfer.id,
            from_status=None,
            to_status=TransferStatus.PREPARED.value,
            occurred_at=now,
        )
    )


def request_interlibrary_loan(
    session: Session,
    *,
    member_id: int,
    copy_id: int,
    destination_branch_id: int,
    idempotency_key: str,
    now: datetime,
) -> tuple[Loan, bool]:
    """Returns (loan, created). `created` is False for an idempotent replay."""
    request_hash = canonical_request_hash(
        OPERATION.value,
        {
            "member_id": member_id,
            "copy_id": copy_id,
            "destination_branch_id": destination_branch_id,
        },
    )
    loan_id = session.execute(
        text("SELECT nextval(pg_get_serial_sequence('loans', 'id'))")
    ).scalar_one()

    # 1. Claim. If another transaction holds the same key uncommitted, this statement waits
    #    for it: after its commit we see the row (replay), after its rollback we win.
    if not _claim_idempotency_key(session, idempotency_key, request_hash, loan_id, now):
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

    # 2. Lock the copy, then 3. validate under the lock.
    copy = lock_copy(session, copy_id)
    member = session.get(Member, member_id)
    if member is None:
        raise NotFoundError("member_not_found", f"Member {member_id} does not exist.")
    destination = session.get(Branch, destination_branch_id)
    if destination is None:
        raise NotFoundError("branch_not_found", f"Branch {destination_branch_id} does not exist.")
    origin = session.get(Branch, copy.owning_branch_id)

    if copy.status != CopyStatus.AVAILABLE.value:
        raise ConflictError(
            "copy_not_available", f"Copy {copy.id} is {copy.status}, not AVAILABLE."
        )
    if copy.current_branch_id != copy.owning_branch_id:
        raise ConflictError(
            "copy_not_at_owning_branch", f"Copy {copy.id} is not at its owning branch."
        )
    if not member.enabled:
        raise ConflictError("member_disabled", f"Member {member.id} is not enabled.")
    if destination.id == origin.id:
        raise ConflictError("same_branch", "Destination must differ from the copy's owning branch.")
    if not (origin.active and destination.active):
        raise ConflictError("branch_inactive", "Origin and destination branches must be active.")

    # 4. Write.
    loan = Loan(
        id=loan_id,
        kind=LoanKind.INTERLIBRARY.value,
        member_id=member.id,
        copy_id=copy.id,
        origin_branch_id=origin.id,
        destination_branch_id=destination.id,
        status=LoanStatus.REQUESTED.value,
        requested_at=now,
    )
    session.add(loan)
    session.flush()
    transfer = Transfer(
        loan_id=loan.id,
        direction=TransferDirection.OUTBOUND.value,
        origin_branch_id=origin.id,
        destination_branch_id=destination.id,
        status=TransferStatus.PREPARED.value,
        created_at=now,
    )
    session.add(transfer)
    session.flush()
    _add_initial_history(session, transfer, now)
    copy.status = CopyStatus.RESERVED.value
    session.flush()
    return loan, True
