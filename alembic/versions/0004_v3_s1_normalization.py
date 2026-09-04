"""V3-S1: Normalization tables.

Creates normalized_values (E4) table with indexes and constraints.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-04

"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # normalized_values (E4)
    op.create_table(
        "normalized_values",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("extracted_value_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.Text(), nullable=False),
        sa.Column("normalization_rule", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["owner_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["extracted_value_id"], ["extracted_values.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_norm_extracted", "normalized_values", ["extracted_value_id"])
    op.create_index("idx_norm_owner", "normalized_values", ["owner_id"])


def downgrade() -> None:
    op.drop_index("idx_norm_owner", table_name="normalized_values")
    op.drop_index("idx_norm_extracted", table_name="normalized_values")
    op.drop_table("normalized_values")
