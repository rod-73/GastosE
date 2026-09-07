"""Phase 3: Payments table (E12).

Creates the payments table for expense payments.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-07

"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # payments (E12)
    op.create_table(
        "payments",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expense_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_method_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("amount_paid", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["owner_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payment_method_id"], ["payment_methods.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_payments_owner_id", "payments", ["owner_id"])
    op.create_index("ix_payments_expense_id", "payments", ["expense_id"])


def downgrade() -> None:
    op.drop_index("ix_payments_expense_id", table_name="payments")
    op.drop_index("ix_payments_owner_id", table_name="payments")
    op.drop_table("payments")
