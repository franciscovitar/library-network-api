"""Isolated guest workspaces and synthetic branch/member membership.

Revision ID: 0004
Revises: 0003
Date: 2026-11-23

Additive only. Existing staff, loans, branches and interlibrary data remain intact.
No guest rows are seeded by this migration.
"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demo_workspaces",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("subject", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_demo_workspaces")),
        sa.UniqueConstraint("subject", name=op.f("uq_demo_workspaces_subject")),
    )
    op.create_index("ix_demo_workspaces_expires_at", "demo_workspaces", ["expires_at"])
    op.create_table(
        "demo_workspace_branches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.BigInteger(), nullable=False),
        sa.Column("branch_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_demo_workspace_branches")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["demo_workspaces.id"],
            name=op.f("fk_demo_workspace_branches_workspace_id_demo_workspaces"),
        ),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["branches.id"],
            name=op.f("fk_demo_workspace_branches_branch_id_branches"),
        ),
        sa.UniqueConstraint(
            "workspace_id", "branch_id", name=op.f("uq_demo_workspace_branches_pair")
        ),
        sa.UniqueConstraint("branch_id", name=op.f("uq_demo_workspace_branches_branch_id")),
    )
    op.create_index(
        "ix_demo_workspace_branches_workspace_id",
        "demo_workspace_branches",
        ["workspace_id"],
    )
    op.create_table(
        "demo_workspace_members",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.BigInteger(), nullable=False),
        sa.Column("member_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_demo_workspace_members")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["demo_workspaces.id"],
            name=op.f("fk_demo_workspace_members_workspace_id_demo_workspaces"),
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["members.id"],
            name=op.f("fk_demo_workspace_members_member_id_members"),
        ),
        sa.UniqueConstraint(
            "workspace_id", "member_id", name=op.f("uq_demo_workspace_members_pair")
        ),
        sa.UniqueConstraint("member_id", name=op.f("uq_demo_workspace_members_member_id")),
    )
    op.create_index(
        "ix_demo_workspace_members_workspace_id",
        "demo_workspace_members",
        ["workspace_id"],
    )


def downgrade() -> None:
    conn = op.get_bind()
    for table in ("demo_workspace_members", "demo_workspace_branches", "demo_workspaces"):
        if conn.scalar(sa.text(f"SELECT count(*) FROM {table}")):
            raise RuntimeError(
                "Downgrade blocked: guest workspace data exists. Use an approved "
                "cleanup/backup workflow before removing the schema."
            )
    op.drop_index("ix_demo_workspace_members_workspace_id", table_name="demo_workspace_members")
    op.drop_table("demo_workspace_members")
    op.drop_index("ix_demo_workspace_branches_workspace_id", table_name="demo_workspace_branches")
    op.drop_table("demo_workspace_branches")
    op.drop_index("ix_demo_workspaces_expires_at", table_name="demo_workspaces")
    op.drop_table("demo_workspaces")
