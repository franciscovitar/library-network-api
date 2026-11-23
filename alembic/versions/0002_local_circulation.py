"""Add branch-local loans while preserving interlibrary invariants.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-23

Existing loans keep INTERLIBRARY as their default kind.
A downgrade refuses to discard local loan records or their idempotency claims.
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "loans",
        sa.Column("kind", sa.String(16), nullable=False, server_default="INTERLIBRARY"),
    )
    op.create_check_constraint(
        op.f("ck_loans_kind_valid"), "loans", "kind IN ('INTERLIBRARY', 'LOCAL')"
    )
    op.drop_constraint(op.f("ck_loans_branches_differ"), "loans", type_="check")
    op.create_check_constraint(
        op.f("ck_loans_branches_differ"),
        "loans",
        "(kind = 'INTERLIBRARY' AND origin_branch_id <> destination_branch_id) OR "
        "(kind = 'LOCAL' AND origin_branch_id = destination_branch_id)",
    )
    op.drop_constraint(
        "ck_idempotency_records_operation_valid", "idempotency_records", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_idempotency_records_operation_valid"),
        "idempotency_records",
        "operation IN ('INTERLIBRARY_REQUEST', 'LOCAL_REQUEST')",
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT COUNT(*) FROM loans WHERE kind = 'LOCAL'")):
        raise RuntimeError("Downgrade blocked: local loans exist and must be explicitly migrated.")
    if connection.scalar(
        sa.text("SELECT COUNT(*) FROM idempotency_records WHERE operation = 'LOCAL_REQUEST'")
    ):
        raise RuntimeError("Downgrade blocked: local idempotency claims exist.")
    op.drop_constraint(
        "ck_idempotency_records_operation_valid", "idempotency_records", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_idempotency_records_operation_valid"),
        "idempotency_records",
        "operation IN ('INTERLIBRARY_REQUEST')",
    )
    op.drop_constraint(op.f("ck_loans_branches_differ"), "loans", type_="check")
    op.create_check_constraint(
        op.f("ck_loans_branches_differ"), "loans", "origin_branch_id <> destination_branch_id"
    )
    op.drop_constraint(op.f("ck_loans_kind_valid"), "loans", type_="check")
    op.drop_column("loans", "kind")
