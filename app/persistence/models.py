"""Relational model for V1.1 (branches, members, books, copies, loans, transfers, history).

Design rules:
- PostgreSQL enforces integrity (FKs, CHECKs, unique + partial unique indexes); application
  code will be the first line of defence, these constraints the second.
- Timestamps are timezone-aware (UTC) and set by the application/injectable clock, so no
  `now()` server defaults: tests and the seed stay deterministic.
- No unsynchronised `available` boolean: availability is `copies.status`.
- State vocabularies are VARCHAR + CHECK generated from `app.domain.states`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.domain.states import (
    LEGAL_TRANSFER_STEPS,
    NONTERMINAL_LOAN_STATUSES,
    CopyStatus,
    IdempotentOperation,
    LoanKind,
    LoanStatus,
    PhysicalCondition,
    TransferDirection,
    TransferStatus,
)

# Deterministic constraint/index names keep Alembic migrations stable and reviewable.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def _in(column: str, values: tuple[StrEnum, ...] | type[StrEnum]) -> str:
    quoted = ", ".join(f"'{v.value}'" for v in values)
    return f"{column} IN ({quoted})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _id() -> Mapped[int]:
    return mapped_column(BigInteger, primary_key=True, autoincrement=True)


def _tstz(nullable: bool = False) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=nullable)


class Branch(Base):
    """Synthetic library branch (academic 'sede')."""

    __tablename__ = "branches"

    id: Mapped[int] = _id()
    name: Mapped[str] = mapped_column(String(120), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class Member(Base):
    """Synthetic member. Holds no real personal data (no DNI, email, name)."""

    __tablename__ = "members"

    id: Mapped[int] = _id()
    code: Mapped[str] = mapped_column(String(32), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = _id()
    isbn: Mapped[str] = mapped_column(String(20), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    author: Mapped[str] = mapped_column(String(120))


class Copy(Base):
    """Physical copy ('ejemplar'). `owning_branch_id` never changes; `current_branch_id`
    changes only when a transfer is RECEIVED (enforced by the future application layer)."""

    __tablename__ = "copies"
    __table_args__ = (
        CheckConstraint(_in("status", CopyStatus), name="status_valid"),
        CheckConstraint(_in("physical_condition", PhysicalCondition), name="condition_valid"),
        Index("ix_copies_book_id", "book_id"),
        # "which copies are available at branch X" is the hot catalogue query.
        Index("ix_copies_current_branch_id_status", "current_branch_id", "status"),
    )

    id: Mapped[int] = _id()
    code: Mapped[str] = mapped_column(String(32), unique=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"))
    owning_branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    current_branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    status: Mapped[str] = mapped_column(String(16), server_default=CopyStatus.AVAILABLE.value)
    physical_condition: Mapped[str] = mapped_column(
        String(16), server_default=PhysicalCondition.GOOD.value
    )

    book: Mapped[Book] = relationship()


class Loan(Base):
    """Interlibrary loan. Nonterminal until the return transfer is received (V1.1):
    REQUESTED -> ACTIVE -> RETURNING -> CLOSED."""

    __tablename__ = "loans"
    __table_args__ = (
        CheckConstraint(_in("status", LoanStatus), name="status_valid"),
        CheckConstraint(
            "return_condition IS NULL OR " + _in("return_condition", PhysicalCondition),
            name="return_condition_valid",
        ),
        CheckConstraint(
            "(kind = 'INTERLIBRARY' AND origin_branch_id <> destination_branch_id) OR "
            "(kind = 'LOCAL' AND origin_branch_id = destination_branch_id)",
            name="branches_differ",
        ),
        CheckConstraint(_in("kind", LoanKind), name="kind_valid"),
        # Date/state coherence: each state implies which timestamps must exist.
        CheckConstraint(
            f"status = '{LoanStatus.REQUESTED}' OR (started_at IS NOT NULL AND due_at IS NOT NULL)",
            name="started_after_requested",
        ),
        CheckConstraint("due_at IS NULL OR due_at > started_at", name="due_after_start"),
        CheckConstraint(
            f"(status IN ('{LoanStatus.RETURNING}', '{LoanStatus.CLOSED}')) = "
            "(borrower_returned_at IS NOT NULL AND return_condition IS NOT NULL)",
            name="return_fields_match_status",
        ),
        CheckConstraint(
            f"(status = '{LoanStatus.CLOSED}') = (closed_at IS NOT NULL)",
            name="closed_at_matches_status",
        ),
        # At most ONE nonterminal loan per copy. A borrower hand-back (RETURNING) keeps the
        # loan nonterminal, so the copy cannot be re-requested until it is back and CLOSED.
        Index(
            "uq_loans_copy_id_nonterminal",
            "copy_id",
            unique=True,
            postgresql_where=text(_in("status", NONTERMINAL_LOAN_STATUSES)),
        ),
        Index("ix_loans_copy_id", "copy_id"),
        Index("ix_loans_member_id", "member_id"),
    )

    id: Mapped[int] = _id()
    kind: Mapped[str] = mapped_column(String(16), server_default=LoanKind.INTERLIBRARY.value)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    copy_id: Mapped[int] = mapped_column(ForeignKey("copies.id"))
    origin_branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    destination_branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    status: Mapped[str] = mapped_column(String(16))
    requested_at: Mapped[datetime] = _tstz()
    started_at: Mapped[datetime | None] = _tstz(nullable=True)
    due_at: Mapped[datetime | None] = _tstz(nullable=True)
    # Borrower hand-back is distinct from logistics completion (closed_at).
    borrower_returned_at: Mapped[datetime | None] = _tstz(nullable=True)
    closed_at: Mapped[datetime | None] = _tstz(nullable=True)
    return_condition: Mapped[str | None] = mapped_column(String(16), nullable=True)

    transfers: Mapped[list[Transfer]] = relationship(back_populates="loan", order_by="Transfer.id")


class Transfer(Base):
    """Shipment note ('remito') moving a copy between branches. At most one OUTBOUND and
    one RETURN transfer per loan."""

    __tablename__ = "transfers"
    __table_args__ = (
        UniqueConstraint("loan_id", "direction", name="uq_transfers_loan_id_direction"),
        CheckConstraint(_in("direction", TransferDirection), name="direction_valid"),
        CheckConstraint(_in("status", TransferStatus), name="status_valid"),
        CheckConstraint("origin_branch_id <> destination_branch_id", name="branches_differ"),
        CheckConstraint(
            f"(status = '{TransferStatus.RECEIVED}') = (received_at IS NOT NULL)",
            name="received_at_matches_status",
        ),
    )

    id: Mapped[int] = _id()
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id"))
    direction: Mapped[str] = mapped_column(String(16))
    origin_branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    destination_branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = _tstz()
    received_at: Mapped[datetime | None] = _tstz(nullable=True)

    loan: Mapped[Loan] = relationship(back_populates="transfers")
    events: Mapped[list[TransferEvent]] = relationship(
        back_populates="transfer", order_by="TransferEvent.id"
    )


_LEGAL_STEP_SQL = " OR ".join(
    f"(from_status = '{a}' AND to_status = '{b}')" for a, b in LEGAL_TRANSFER_STEPS
)


class TransferEvent(Base):
    """Append-only history. The initial PREPARED event has `from_status` NULL."""

    __tablename__ = "transfer_events"
    __table_args__ = (
        # Each state is entered at most once per transfer: duplicate receipts cannot
        # produce duplicate history.
        UniqueConstraint(
            "transfer_id", "to_status", name="uq_transfer_events_transfer_id_to_status"
        ),
        CheckConstraint(_in("to_status", TransferStatus), name="to_status_valid"),
        CheckConstraint(
            "from_status IS NULL OR " + _in("from_status", TransferStatus),
            name="from_status_valid",
        ),
        CheckConstraint(
            f"(from_status IS NULL) = (to_status = '{TransferStatus.PREPARED}')",
            name="initial_event_is_prepared",
        ),
        CheckConstraint(f"from_status IS NULL OR ({_LEGAL_STEP_SQL})", name="step_is_legal"),
    )

    id: Mapped[int] = _id()
    transfer_id: Mapped[int] = mapped_column(ForeignKey("transfers.id"))
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str] = mapped_column(String(16))
    occurred_at: Mapped[datetime] = _tstz()

    transfer: Mapped[Transfer] = relationship(back_populates="events")


class IdempotencyRecord(Base):
    """Claim of an `(operation, Idempotency-Key)` pair.

    `resource_id` is NOT NULL and references the loan through a DEFERRABLE INITIALLY
    DEFERRED foreign key: the application can claim the key with a pre-allocated loan id
    and insert the loan later in the same transaction. A committed key without its
    resource is therefore impossible (commit fails), as required by the V1.1 contract.
    """

    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("operation", "key", name="uq_idempotency_records_operation_key"),
        CheckConstraint(_in("operation", IdempotentOperation), name="operation_valid"),
        CheckConstraint("resource_type = 'LOAN'", name="resource_type_valid"),
        CheckConstraint("char_length(request_hash) = 64", name="request_hash_is_sha256_hex"),
        CheckConstraint("char_length(key) BETWEEN 1 AND 128", name="key_length"),
    )

    id: Mapped[int] = _id()
    operation: Mapped[str] = mapped_column(String(40))
    key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(16), server_default="LOAN")
    resource_id: Mapped[int] = mapped_column(
        ForeignKey("loans.id", deferrable=True, initially="DEFERRED")
    )
    created_at: Mapped[datetime] = _tstz()


class StaffUser(Base):
    """Provisioned staff identity; no public self-registration endpoint."""

    __tablename__ = "staff_users"

    id: Mapped[int] = _id()
    subject: Mapped[str] = mapped_column(String(180), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class StaffBranchGrant(Base):
    """Server-owned authorization, never inferred from JWT role claims."""

    __tablename__ = "staff_branch_grants"
    __table_args__ = (
        UniqueConstraint("staff_user_id", "branch_id", name="uq_staff_branch_grants_user_branch"),
        CheckConstraint(
            "role IN ('VIEWER', 'LIBRARIAN', 'BRANCH_MANAGER', 'NETWORK_ADMIN')",
            name="role_valid",
        ),
        Index("ix_staff_branch_grants_branch_id", "branch_id"),
    )

    id: Mapped[int] = _id()
    staff_user_id: Mapped[int] = mapped_column(ForeignKey("staff_users.id"))
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    role: Mapped[str] = mapped_column(String(24))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class DemoWorkspace(Base):
    """A short-lived, isolated synthetic library owned by an opaque guest subject."""

    __tablename__ = "demo_workspaces"
    __table_args__ = (Index("ix_demo_workspaces_expires_at", "expires_at"),)

    id: Mapped[int] = _id()
    subject: Mapped[str] = mapped_column(String(50), unique=True)
    created_at: Mapped[datetime] = _tstz()
    expires_at: Mapped[datetime] = _tstz()
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class DemoWorkspaceBranch(Base):
    """One branch belongs to exactly one guest workspace, never shared."""

    __tablename__ = "demo_workspace_branches"
    __table_args__ = (
        UniqueConstraint("workspace_id", "branch_id", name="uq_demo_workspace_branches_pair"),
        UniqueConstraint("branch_id", name="uq_demo_workspace_branches_branch_id"),
        Index("ix_demo_workspace_branches_workspace_id", "workspace_id"),
    )

    id: Mapped[int] = _id()
    workspace_id: Mapped[int] = mapped_column(ForeignKey("demo_workspaces.id"))
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))


class DemoWorkspaceMember(Base):
    """A synthetic member belongs to exactly one guest workspace."""

    __tablename__ = "demo_workspace_members"
    __table_args__ = (
        UniqueConstraint("member_id", name="uq_demo_workspace_members_member_id"),
        UniqueConstraint("workspace_id", "member_id", name="uq_demo_workspace_members_pair"),
        Index("ix_demo_workspace_members_workspace_id", "workspace_id"),
    )

    id: Mapped[int] = _id()
    workspace_id: Mapped[int] = mapped_column(ForeignKey("demo_workspaces.id"))
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
