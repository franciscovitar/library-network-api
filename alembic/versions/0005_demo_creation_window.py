"""Bound anonymous workspace creation on PostgreSQL (global budget).

Revision ID: 0005
Revises: 0004
Date: 2026-11-23
Additive metadata only; no existing data touched.
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demo_creation_windows",
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_count", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("window_start", name=op.f("pk_demo_creation_windows")),
        sa.CheckConstraint("created_count >= 0", name=op.f("ck_demo_creation_windows_nonnegative")),
    )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.scalar(sa.text("SELECT count(*) FROM demo_creation_windows")):
        raise RuntimeError(
            "Downgrade blocked: creation budget evidence exists. "
            "Remove it only through an approved migration procedure."
        )
    op.drop_table("demo_creation_windows")
