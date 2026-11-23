"""Consistent branch-operational metrics from one PostgreSQL statement."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.domain.states import CopyStatus, LoanStatus, TransferStatus
from app.persistence.models import Copy, Loan, Transfer


def get_branch_overview(session: Session, *, branch_id: int, now: datetime) -> dict[str, int]:
    """One statement gives all counts the same MVCC snapshot (no patron records)."""
    totals = (
        select(func.count())
        .select_from(Copy)
        .where(Copy.current_branch_id == branch_id)
        .scalar_subquery()
    )
    available = (
        select(func.count())
        .select_from(Copy)
        .where(
            Copy.current_branch_id == branch_id,
            Copy.status == CopyStatus.AVAILABLE.value,
        )
        .scalar_subquery()
    )
    titles = (
        select(func.count(distinct(Copy.book_id)))
        .where(Copy.current_branch_id == branch_id)
        .scalar_subquery()
    )
    active = (
        select(func.count())
        .select_from(Loan)
        .where(
            Loan.destination_branch_id == branch_id,
            Loan.status == LoanStatus.ACTIVE.value,
        )
        .scalar_subquery()
    )
    overdue = (
        select(func.count())
        .select_from(Loan)
        .where(
            Loan.destination_branch_id == branch_id,
            Loan.status == LoanStatus.ACTIVE.value,
            Loan.due_at < now,
        )
        .scalar_subquery()
    )
    pending_returns = (
        select(func.count())
        .select_from(Loan)
        .where(
            Loan.destination_branch_id == branch_id,
            Loan.status == LoanStatus.RETURNING.value,
        )
        .scalar_subquery()
    )
    arrivals = (
        select(func.count())
        .select_from(Transfer)
        .where(
            Transfer.destination_branch_id == branch_id,
            Transfer.status != TransferStatus.RECEIVED.value,
        )
        .scalar_subquery()
    )
    dispatches = (
        select(func.count())
        .select_from(Transfer)
        .where(
            Transfer.origin_branch_id == branch_id,
            Transfer.status != TransferStatus.RECEIVED.value,
        )
        .scalar_subquery()
    )
    statement = select(
        totals.label("total_copies"),
        available.label("available_copies"),
        titles.label("catalog_titles"),
        active.label("active_loans"),
        overdue.label("overdue_loans"),
        pending_returns.label("pending_returns"),
        arrivals.label("pending_arrivals"),
        dispatches.label("pending_dispatches"),
    )
    counts = session.execute(statement).mappings().one()
    return {"branch_id": branch_id, **dict(counts)}
