"""V3-S3: Expense creation tables.

Creates expenses (E6), expense_lines (E7), and tax_lines (E8) tables.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-04

"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # expenses (E6)
    op.create_table(
        "expenses",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_number", sa.Text(), nullable=True),
        sa.Column("document_date", sa.Date(), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("base_total", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("vat_total", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("withholding_total", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("category_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payment_method_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("state", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("accepted_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_snapshot", sa.Text(), nullable=True),
        sa.Column("voided_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["owner_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id"], ["source_documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["currency"], ["currencies.code"], ondelete="RESTRICT"),
        sa.CheckConstraint("total >= 0", name="ck_expenses_total_nonneg"),
        sa.CheckConstraint(
            "state IN ('draft', 'under_review', 'validation_error', 'duplicate', "
            "'ready_for_acceptance', 'accepted', 'voided', 'rejected', "
            "'confirmed_duplicate', 'failed')",
            name="ck_expenses_state",
        ),
    )
    op.create_index("idx_exp_owner", "expenses", ["owner_id"])
    op.create_index("idx_exp_document", "expenses", ["document_id"])
    op.create_index("idx_exp_supplier", "expenses", ["supplier_id"])
    op.create_index("idx_exp_state", "expenses", ["state"])

    # expense_lines (E7)
    op.create_table(
        "expense_lines",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expense_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("tax_rate_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["owner_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tax_rate_id"], ["tax_rates.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("amount >= 0", name="ck_expense_lines_amount_nonneg"),
    )
    op.create_index("idx_el_expense", "expense_lines", ["expense_id"])
    op.create_index("idx_el_owner", "expense_lines", ["owner_id"])

    # tax_lines (E8)
    op.create_table(
        "tax_lines",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expense_line_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expense_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tax_type", sa.Text(), nullable=False),
        sa.Column("tax_rate_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("taxable_base", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["owner_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["expense_line_id"], ["expense_lines.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tax_rate_id"], ["tax_rates.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("taxable_base >= 0", name="ck_tax_lines_base_nonneg"),
        sa.CheckConstraint("tax_amount >= 0", name="ck_tax_lines_amount_nonneg"),
        sa.CheckConstraint(
            "tax_type IN ('vat', 'withholding')",
            name="ck_tax_lines_type",
        ),
        sa.CheckConstraint(
            "expense_line_id IS NOT NULL OR expense_id IS NOT NULL",
            name="ck_tax_lines_parent",
        ),
    )
    op.create_index("idx_tl_expense", "tax_lines", ["expense_id"])
    op.create_index("idx_tl_line", "tax_lines", ["expense_line_id"])
    op.create_index("idx_tl_owner", "tax_lines", ["owner_id"])


def downgrade() -> None:
    op.drop_index("idx_tl_owner", table_name="tax_lines")
    op.drop_index("idx_tl_line", table_name="tax_lines")
    op.drop_index("idx_tl_expense", table_name="tax_lines")
    op.drop_table("tax_lines")
    op.drop_index("idx_el_owner", table_name="expense_lines")
    op.drop_index("idx_el_expense", table_name="expense_lines")
    op.drop_table("expense_lines")
    op.drop_index("idx_exp_state", table_name="expenses")
    op.drop_index("idx_exp_supplier", table_name="expenses")
    op.drop_index("idx_exp_document", table_name="expenses")
    op.drop_index("idx_exp_owner", table_name="expenses")
    op.drop_table("expenses")
