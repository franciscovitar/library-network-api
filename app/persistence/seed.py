"""Deterministic synthetic seed data for the local demo and tests.

Everything here is invented: no real people, members, ISBNs or library inventory. Ids are
explicit so that documentation, demos and tests can refer to stable identifiers.

Safety: the seed is **insert-only and refuses to touch a non-empty database**. If any seeded
table already contains rows it does nothing and says so; it never updates or deletes data.

Run (after `alembic upgrade head`):  python -m app.persistence.seed
"""

from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.domain.states import CopyStatus, PhysicalCondition
from app.persistence.models import Book, Branch, Copy, Member

BRANCHES = [
    (1, "Central Branch"),
    (2, "North Branch"),
    (3, "South Branch"),
]

# M0006 is intentionally disabled: it exercises the "member must still be enabled" rule.
MEMBERS = [(i, f"M{i:04d}", i != 6) for i in range(1, 7)]

# Synthetic ISBN-like identifiers (prefix 000 is not assigned to any real publisher).
BOOKS = [
    (1, "000-0-0000-0001-1", "Synthetic Tales of the Harbour", "A. Example"),
    (2, "000-0-0000-0002-8", "Introduction to Imaginary Algebra", "B. Sample"),
    (3, "000-0-0000-0003-5", "The Garden of Test Data", "C. Placeholder"),
    (4, "000-0-0000-0004-2", "Maps of Nowhere", "D. Fixture"),
    (5, "000-0-0000-0005-9", "A Short History of Mock Libraries", "E. Stub"),
]

# (id, code, book_id, owning_branch_id, status, condition). Copies start at their owning
# branch, so current_branch_id == owning_branch_id.
COPIES = [
    (1, "CP-0001", 1, 1, CopyStatus.AVAILABLE, PhysicalCondition.GOOD),
    (2, "CP-0002", 1, 2, CopyStatus.AVAILABLE, PhysicalCondition.GOOD),
    (3, "CP-0003", 2, 1, CopyStatus.AVAILABLE, PhysicalCondition.GOOD),
    (4, "CP-0004", 2, 3, CopyStatus.AVAILABLE, PhysicalCondition.GOOD),
    (5, "CP-0005", 3, 2, CopyStatus.AVAILABLE, PhysicalCondition.GOOD),
    (6, "CP-0006", 3, 3, CopyStatus.AVAILABLE, PhysicalCondition.GOOD),
    (7, "CP-0007", 4, 1, CopyStatus.AVAILABLE, PhysicalCondition.GOOD),
    (8, "CP-0008", 4, 2, CopyStatus.AVAILABLE, PhysicalCondition.GOOD),
    (9, "CP-0009", 5, 3, CopyStatus.AVAILABLE, PhysicalCondition.GOOD),
    # Retired and damaged: present in the catalogue but never requestable.
    (10, "CP-0010", 5, 1, CopyStatus.RETIRED, PhysicalCondition.DAMAGED),
]

_SEEDED_TABLES = (Branch, Member, Book, Copy)
_SERIAL_TABLES = ("branches", "members", "books", "copies")


def seed_demo_data(session: Session) -> dict[str, int] | None:
    """Insert the synthetic dataset inside the caller's transaction.

    Returns the inserted row counts, or ``None`` (and writes nothing) if any seeded
    table already has rows. The caller commits.
    """
    for model in _SEEDED_TABLES:
        if session.scalar(select(func.count()).select_from(model)):
            return None

    session.add_all(Branch(id=i, name=name, active=True) for i, name in BRANCHES)
    session.add_all(Member(id=i, code=code, enabled=enabled) for i, code, enabled in MEMBERS)
    session.add_all(
        Book(id=i, isbn=isbn, title=title, author=author) for i, isbn, title, author in BOOKS
    )
    session.flush()  # parents first, so copy FKs resolve
    session.add_all(
        Copy(
            id=i,
            code=code,
            book_id=book_id,
            owning_branch_id=branch_id,
            current_branch_id=branch_id,
            status=status.value,
            physical_condition=condition.value,
        )
        for i, code, book_id, branch_id, status, condition in COPIES
    )
    session.flush()

    # Explicit ids bypass the sequences; move them past the seeded maximum so that later
    # application inserts do not collide.
    for table in _SERIAL_TABLES:
        session.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"(SELECT max(id) FROM {table}))"
            )
        )
    return {
        "branches": len(BRANCHES),
        "members": len(MEMBERS),
        "books": len(BOOKS),
        "copies": len(COPIES),
    }


def main() -> None:
    from app.db import get_engine

    with Session(get_engine()) as session, session.begin():
        counts = seed_demo_data(session)
    if counts is None:
        print("Seed skipped: database already contains data (nothing was changed).")
    else:
        print("Seeded synthetic data:", ", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
