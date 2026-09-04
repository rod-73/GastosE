"""V3-S2: Validation tables.

Creates validated_values (E5) table with indexes and constraints.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-04

"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # validated_values (E5)
    op.create_table(
        "validated_values",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("normalized_value_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("validated_value", sa.Text(), nullable=False),
        sa.Column("validation_result", sa.Text(), nullable=False),
        sa.Column("rules_applied", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["owner_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["normalized_value_id"], ["normalized_values.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "validation_result IN ('passed', 'failed', 'warning', 'corrected')",
            name="ck_validated_values_result",
        ),
    )
    op.create_index("idx_vv_normalized", "validated_values", ["normalized_value_id"])
    op.create_index("idx_vv_owner", "validated_values", ["owner_id"])
    op.create_index("idx_vv_field", "validated_values", ["normalized_value_id", "field"])


def downgrade() -> None:
    op.drop_index("idx_vv_field", table_name="validated_values")
    op.drop_index("idx_vv_owner", table_name="validated_values")
    op.drop_index("idx_vv_normalized", table_name="validated_values")
    op.drop_table("validated_values")
