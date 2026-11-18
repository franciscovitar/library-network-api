"""Use case: activate a loan once the outward transfer has been received."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.application.locks import copy_id_of_loan, lock_copy, lock_loan, lock_loan_transfer
from app.domain.errors import ConflictError
from app.domain.rules import LOAN_PERIOD
from app.domain.states import CopyStatus, LoanStatus, TransferDirection, TransferStatus
from app.persistence.models import Loan, Member


def activate_loan(session: Session, *, loan_id: int, now: datetime) -> Loan:
    copy = lock_copy(session, copy_id_of_loan(session, loan_id))
    loan = lock_loan(session, loan_id)
    outbound = lock_loan_transfer(session, loan.id, TransferDirection.OUTBOUND)

    if loan.status != LoanStatus.REQUESTED.value:
        raise ConflictError(
            "loan_not_requested", f"Loan {loan.id} is {loan.status}, not REQUESTED."
        )
    if outbound is None or outbound.status != TransferStatus.RECEIVED.value:
        raise ConflictError(
            "transfer_not_received", "The outward transfer must be RECEIVED before activation."
        )
    if (
        copy.status != CopyStatus.RESERVED.value
        or copy.current_branch_id != loan.destination_branch_id
    ):
        raise ConflictError(
            "copy_state_inconsistent",
            f"Copy {copy.id} must be RESERVED at the destination branch to activate the loan.",
        )
    member = session.get(Member, loan.member_id)  # renewed validation at activation time
    if not member.enabled:
        raise ConflictError("member_disabled", f"Member {member.id} is no longer enabled.")

    loan.status = LoanStatus.ACTIVE.value
    loan.started_at = now
    loan.due_at = now + LOAN_PERIOD
    copy.status = CopyStatus.ON_LOAN.value
    session.flush()
    return loan
