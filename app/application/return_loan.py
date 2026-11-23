"""Use case: the borrower hands the copy back at the destination branch.

Atomically: loan -> RETURNING (still nonterminal), copy -> PENDING_RETURN, and a RETURN
transfer is created PREPARED with its initial history event. The loan only becomes CLOSED
when that return transfer is RECEIVED (see advance_transfer).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.application.locks import copy_id_of_loan, lock_copy, lock_loan
from app.application.request_loan import _add_initial_history
from app.domain.errors import ConflictError
from app.domain.states import (
    CopyStatus,
    LoanKind,
    LoanStatus,
    PhysicalCondition,
    TransferDirection,
    TransferStatus,
)
from app.persistence.models import Loan, Transfer


def return_loan(
    session: Session, *, loan_id: int, condition: PhysicalCondition, now: datetime
) -> Loan:
    copy = lock_copy(session, copy_id_of_loan(session, loan_id))
    loan = lock_loan(session, loan_id)

    if loan.kind != LoanKind.INTERLIBRARY.value:
        raise ConflictError("wrong_loan_kind", "Local loans use local return.")
    if loan.status != LoanStatus.ACTIVE.value:
        raise ConflictError("loan_not_active", f"Loan {loan.id} is {loan.status}, not ACTIVE.")
    if copy.status != CopyStatus.ON_LOAN.value:
        raise ConflictError(
            "copy_state_inconsistent", f"Copy {copy.id} is {copy.status}; expected ON_LOAN."
        )

    loan.status = LoanStatus.RETURNING.value
    loan.borrower_returned_at = now
    loan.return_condition = condition.value
    copy.status = CopyStatus.PENDING_RETURN.value
    session.flush()

    transfer = Transfer(
        loan_id=loan.id,
        direction=TransferDirection.RETURN.value,
        origin_branch_id=loan.destination_branch_id,  # where the borrower left it
        destination_branch_id=copy.owning_branch_id,  # back to its owner
        status=TransferStatus.PREPARED.value,
        created_at=now,
    )
    session.add(transfer)
    session.flush()
    _add_initial_history(session, transfer, now)
    session.flush()
    return loan
