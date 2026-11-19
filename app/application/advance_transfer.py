"""Use case: move a transfer one step forward (PREPARED -> DISPATCHED -> IN_TRANSIT -> RECEIVED).

Locks: copy -> loan -> transfer (after an unlocked lookup of which copy to lock). State is
re-read and validated AFTER the locks are held, so two simultaneous advances serialize and
the loser sees the new state and is rejected without writing anything.

Side effects follow the V1.1 lifecycle; the physical location (`current_branch_id`) changes
only on RECEIVED.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.application.locks import (
    copy_id_of_transfer,
    lock_copy,
    lock_loan,
    lock_transfer,
)
from app.domain.errors import ConflictError
from app.domain.rules import next_transfer_status
from app.domain.states import (
    CopyStatus,
    LoanStatus,
    PhysicalCondition,
    TransferDirection,
    TransferStatus,
)
from app.persistence.models import Copy, Loan, Transfer, TransferEvent


def _require_copy_status(copy: Copy, expected: CopyStatus) -> None:
    if copy.status != expected.value:
        raise ConflictError(
            "copy_state_inconsistent",
            f"Copy {copy.id} is {copy.status}; expected {expected.value} for this step.",
        )


def _append_event(
    session: Session, transfer: Transfer, from_status: str, to_status: TransferStatus, now: datetime
) -> None:
    session.add(
        TransferEvent(
            transfer_id=transfer.id,
            from_status=from_status,
            to_status=to_status.value,
            occurred_at=now,
        )
    )


def _apply_outbound_effects(copy: Copy, transfer: Transfer, target: TransferStatus) -> None:
    if target is TransferStatus.DISPATCHED:
        _require_copy_status(copy, CopyStatus.RESERVED)
        copy.status = CopyStatus.IN_TRANSIT.value
    elif target is TransferStatus.IN_TRANSIT:
        _require_copy_status(copy, CopyStatus.IN_TRANSIT)
    else:  # RECEIVED: the copy physically arrives at the destination
        _require_copy_status(copy, CopyStatus.IN_TRANSIT)
        copy.current_branch_id = transfer.destination_branch_id
        copy.status = CopyStatus.RESERVED.value


def _apply_return_effects(
    copy: Copy, loan: Loan, transfer: Transfer, target: TransferStatus, now: datetime
) -> None:
    if target is TransferStatus.DISPATCHED:
        _require_copy_status(copy, CopyStatus.PENDING_RETURN)
        copy.status = CopyStatus.IN_TRANSIT.value
    elif target is TransferStatus.IN_TRANSIT:
        _require_copy_status(copy, CopyStatus.IN_TRANSIT)
    else:  # RECEIVED at the owning branch: logistics complete, loan closes
        _require_copy_status(copy, CopyStatus.IN_TRANSIT)
        copy.current_branch_id = transfer.destination_branch_id
        if loan.return_condition == PhysicalCondition.GOOD.value:
            copy.status = CopyStatus.AVAILABLE.value
        else:
            copy.status = CopyStatus.RETIRED.value
            copy.physical_condition = PhysicalCondition.DAMAGED.value
        loan.status = LoanStatus.CLOSED.value
        loan.closed_at = now


def advance_transfer(
    session: Session, *, transfer_id: int, next_status: TransferStatus, now: datetime
) -> Transfer:
    copy = lock_copy(session, copy_id_of_transfer(session, transfer_id))
    transfer_loan_id = session.get(Transfer, transfer_id).loan_id  # id only; row locked below
    loan = lock_loan(session, transfer_loan_id)
    transfer = lock_transfer(session, transfer_id)

    # Re-validate under the locks.
    expected = next_transfer_status(TransferStatus(transfer.status))
    if expected is None or expected is not next_status:
        legal = expected.value if expected else "none (transfer is final)"
        raise ConflictError(
            "illegal_transition",
            f"Transfer {transfer.id} is {transfer.status}; cannot move to {next_status.value} "
            f"(only legal next state: {legal}).",
        )
    outbound = transfer.direction == TransferDirection.OUTBOUND.value
    required_loan_status = LoanStatus.REQUESTED if outbound else LoanStatus.RETURNING
    if loan.status != required_loan_status.value:
        raise ConflictError(
            "loan_state_conflict",
            f"Loan {loan.id} is {loan.status}; a {transfer.direction} transfer requires "
            f"{required_loan_status.value}.",
        )

    previous_status = transfer.status
    transfer.status = next_status.value
    if next_status is TransferStatus.RECEIVED:
        transfer.received_at = now
    if outbound:
        _apply_outbound_effects(copy, transfer, next_status)
    else:
        _apply_return_effects(copy, loan, transfer, next_status, now)
    session.flush()  # state changes reach the database before the history row
    _append_event(session, transfer, previous_status, next_status, now)
    session.flush()
    return transfer
