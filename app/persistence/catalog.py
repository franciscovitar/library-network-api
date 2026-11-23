"""Read-only catalogue queries backed by PostgreSQL, not a browser simulation."""

from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.domain.errors import NotFoundError
from app.domain.states import CopyStatus
from app.persistence.models import Book, Branch, Copy


def search_catalog(
    session: Session,
    *,
    q: str | None,
    branch_id: int | None,
    available_only: bool,
    limit: int,
    offset: int,
) -> dict:
    """Count physical copies at the selected branch, or across the entire network."""
    if branch_id is not None and session.get(Branch, branch_id) is None:
        raise NotFoundError("branch_not_found", f"Branch {branch_id} does not exist.")

    join_condition = Copy.book_id == Book.id
    if branch_id is not None:
        join_condition = and_(join_condition, Copy.current_branch_id == branch_id)

    available = func.count(Copy.id).filter(Copy.status == CopyStatus.AVAILABLE.value)
    stmt = (
        select(
            Book.id,
            Book.isbn,
            Book.title,
            Book.author,
            func.count(Copy.id).label("total_copies"),
            available.label("available_copies"),
        )
        .select_from(Book)
        .outerjoin(Copy, join_condition)
        .group_by(Book.id, Book.isbn, Book.title, Book.author)
    )
    if q:
        stmt = stmt.where(
            or_(
                Book.title.icontains(q, autoescape=True),
                Book.author.icontains(q, autoescape=True),
                Book.isbn.icontains(q, autoescape=True),
            )
        )
    if available_only:
        stmt = stmt.having(available > 0)

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.execute(
        stmt.order_by(Book.title, Book.id).limit(limit).offset(offset)
    ).mappings()
    return {
        "items": [dict(row) for row in rows],
        "limit": limit,
        "offset": offset,
        "total": total,
    }
