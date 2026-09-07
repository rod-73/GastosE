"""Phase 3: Manual corrections table (E14).

Creates the manual_corrections table for append-only correction records.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-07

"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # manual_corrections (E14)
    op.create_table(
        "manual_corrections",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expense_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=False),
        sa.Column("new_value", sa.Text(), nullable=False),
        sa.Column("corrected_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["owner_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["corrected_by"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_manual_corrections_owner_id", "manual_corrections", ["owner_id"])
    op.create_index("ix_manual_corrections_expense_id", "manual_corrections", ["expense_id"])


def downgrade() -> None:
    op.drop_index("ix_manual_corrections_expense_id", table_name="manual_corrections")
    op.drop_index("ix_manual_corrections_owner_id", table_name="manual_corrections")
    op.drop_table("manual_corrections")
