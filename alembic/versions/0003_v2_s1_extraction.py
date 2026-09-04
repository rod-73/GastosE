"""V2-S1: Extraction tables.

Creates extractions (E2) and extracted_values (E3) tables with indexes
and constraints.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-04

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # extractions (E2)
    op.create_table(
        "extractions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "method IN ('xml_schema', 'pdf_text_rules', 'ocr', 'vision_llm')",
            name="chk_ext_method",
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'running', 'completed', 'failed', 'reprocessed')",
            name="chk_ext_state",
        ),
        sa.CheckConstraint(
            "state != 'failed' OR failure_reason IS NOT NULL",
            name="chk_ext_failure_reason",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id"], ["source_documents.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_ext_owner", "extractions", ["owner_id"])
    op.create_index("idx_ext_document", "extractions", ["document_id"])
    op.create_index("idx_ext_state", "extractions", ["owner_id", "state"])

    # extracted_values (E3)
    op.create_table(
        "extracted_values",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("extraction_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("provenance", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="chk_extval_confidence",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["extraction_id"], ["extractions.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_extval_extraction", "extracted_values", ["extraction_id"])
    op.create_index("idx_extval_owner", "extracted_values", ["owner_id"])

    # FK from extraction_jobs.extraction_id -> extractions.id
    op.create_foreign_key(
        "fk_jobs_extraction",
        "extraction_jobs",
        "extractions",
        ["extraction_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_jobs_extraction", "extraction_jobs", type_="foreignkey")
    op.drop_index("idx_extval_owner", table_name="extracted_values")
    op.drop_index("idx_extval_extraction", table_name="extracted_values")
    op.drop_table("extracted_values")
    op.drop_index("idx_ext_state", table_name="extractions")
    op.drop_index("idx_ext_document", table_name="extractions")
    op.drop_index("idx_ext_owner", table_name="extractions")
    op.drop_table("extractions")
