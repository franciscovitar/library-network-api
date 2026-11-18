"""Read-only queries used by the GET endpoints (bounded, parameterized, no arbitrary SQL)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.errors import NotFoundError
from app.persistence.models import Book, Branch, Copy, Loan, Transfer

MAX_PAGE_SIZE = 100


def list_branches(session: Session) -> list[Branch]:
    return list(session.scalars(select(Branch).order_by(Branch.id)))


def list_books(session: Session, *, limit: int, offset: int) -> tuple[list[Book], int]:
    total = session.scalar(select(func.count()).select_from(Book)) or 0
    rows = session.scalars(select(Book).order_by(Book.id).limit(limit).offset(offset))
    return list(rows), total


def get_copy(session: Session, copy_id: int) -> Copy:
    copy = session.get(Copy, copy_id)
    if copy is None:
        raise NotFoundError("copy_not_found", f"Copy {copy_id} does not exist.")
    return copy


def get_loan(session: Session, loan_id: int) -> Loan:
    loan = session.get(Loan, loan_id)
    if loan is None:
        raise NotFoundError("loan_not_found", f"Loan {loan_id} does not exist.")
    return loan


def get_transfer(session: Session, transfer_id: int) -> Transfer:
    transfer = session.get(Transfer, transfer_id)
    if transfer is None:
        raise NotFoundError("transfer_not_found", f"Transfer {transfer_id} does not exist.")
    return transfer
