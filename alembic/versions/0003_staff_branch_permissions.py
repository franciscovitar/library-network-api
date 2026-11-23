"""Add staff identities and explicit branch grants; seed no implicit accounts.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-23

Every principal fails closed until separately provisioned by a trusted operator.
"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("subject", sa.String(180), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_users")),
        sa.UniqueConstraint("subject", name=op.f("uq_staff_users_subject")),
    )
    op.create_table(
        "staff_branch_grants",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("staff_user_id", sa.BigInteger(), nullable=False),
        sa.Column("branch_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_branch_grants")),
        sa.ForeignKeyConstraint(
            ["staff_user_id"],
            ["staff_users.id"],
            name=op.f("fk_staff_branch_grants_staff_user_id_staff_users"),
        ),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["branches.id"],
            name=op.f("fk_staff_branch_grants_branch_id_branches"),
        ),
        sa.UniqueConstraint(
            "staff_user_id", "branch_id", name=op.f("uq_staff_branch_grants_user_branch")
        ),
        sa.CheckConstraint(
            "role IN ('VIEWER', 'LIBRARIAN', 'BRANCH_MANAGER', 'NETWORK_ADMIN')",
            name=op.f("ck_staff_branch_grants_role_valid"),
        ),
    )
    op.create_index("ix_staff_branch_grants_branch_id", "staff_branch_grants", ["branch_id"])


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM staff_branch_grants")):
        raise RuntimeError("Downgrade blocked: staff grants exist; export and revoke first.")
    if connection.scalar(sa.text("SELECT count(*) FROM staff_users")):
        raise RuntimeError("Downgrade blocked: staff users exist; export first.")
    op.drop_index("ix_staff_branch_grants_branch_id", table_name="staff_branch_grants")
    op.drop_table("staff_branch_grants")
    op.drop_table("staff_users")
