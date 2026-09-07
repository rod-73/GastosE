"""Phase 3: Document splits tables (E19).

Creates the document_splits and split_expenses tables.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-07

"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # document_splits (E19)
    op.create_table(
        "document_splits",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["owner_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id"], ["source_documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_document_splits_owner_id", "document_splits", ["owner_id"])
    op.create_index("ix_document_splits_document_id", "document_splits", ["document_id"])

    # split_expenses (intermediate table)
    op.create_table(
        "split_expenses",
        sa.Column("split_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("expense_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.ForeignKeyConstraint(["split_id"], ["document_splits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("split_id", "expense_id", name="uq_split_expenses"),
    )


def downgrade() -> None:
    op.drop_table("split_expenses")
    op.drop_index("ix_document_splits_document_id", table_name="document_splits")
    op.drop_index("ix_document_splits_owner_id", table_name="document_splits")
    op.drop_table("document_splits")
