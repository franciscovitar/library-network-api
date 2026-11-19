"""Row-locking helpers. Always call in the order copy -> loan -> transfer."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.errors import NotFoundError
from app.domain.states import TransferDirection
from app.persistence.models import Copy, Loan, Transfer


def lock_copy(session: Session, copy_id: int) -> Copy:
    copy = session.scalars(
        select(Copy)
        .where(Copy.id == copy_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if copy is None:
        raise NotFoundError("copy_not_found", f"Copy {copy_id} does not exist.")
    return copy


def lock_loan(session: Session, loan_id: int) -> Loan:
    loan = session.scalars(
        select(Loan)
        .where(Loan.id == loan_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if loan is None:
        raise NotFoundError("loan_not_found", f"Loan {loan_id} does not exist.")
    return loan


def lock_transfer(session: Session, transfer_id: int) -> Transfer:
    transfer = session.scalars(
        select(Transfer)
        .where(Transfer.id == transfer_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if transfer is None:
        raise NotFoundError("transfer_not_found", f"Transfer {transfer_id} does not exist.")
    return transfer


def lock_loan_transfer(
    session: Session, loan_id: int, direction: TransferDirection
) -> Transfer | None:
    return session.scalars(
        select(Transfer)
        .where(Transfer.loan_id == loan_id, Transfer.direction == direction.value)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()


def copy_id_of_loan(session: Session, loan_id: int) -> int:
    """Unlocked lookup used only to learn WHICH copy to lock first."""
    copy_id = session.scalar(select(Loan.copy_id).where(Loan.id == loan_id))
    if copy_id is None:
        raise NotFoundError("loan_not_found", f"Loan {loan_id} does not exist.")
    return copy_id


def copy_id_of_transfer(session: Session, transfer_id: int) -> int:
    copy_id = session.scalar(
        select(Loan.copy_id)
        .join(Transfer, Transfer.loan_id == Loan.id)
        .where(Transfer.id == transfer_id)
    )
    if copy_id is None:
        raise NotFoundError("transfer_not_found", f"Transfer {transfer_id} does not exist.")
    return copy_id
