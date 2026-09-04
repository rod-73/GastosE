"""V1-S1: Document ingestion tables.

Creates source_documents, extraction_jobs, duplications, audit_events,
and idempotency_keys tables with indexes and constraints.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-04

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # source_documents (E1)
    op.create_table(
        "source_documents",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("safe_name", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=True),
        sa.Column("fingerprint_sha256", sa.Char(length=64), nullable=False),
        sa.Column("doc_type", sa.Text(), nullable=False),
        sa.Column("format_detected", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("uploaded_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("state", sa.Text(), nullable=False, server_default="uploaded"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("dup_key", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "doc_type IN ('received_invoice', 'ticket', 'other')",
            name="chk_docs_type",
        ),
        sa.CheckConstraint(
            "format_detected IN ('xml', 'pdf_text', 'pdf_scanned', 'image')",
            name="chk_docs_format",
        ),
        sa.CheckConstraint("size_bytes >= 0", name="chk_docs_size"),
        sa.CheckConstraint(
            "state IN ('uploaded', 'processing', 'extracted', 'uncertain', "
            "'validation_error', 'duplicate', 'manually_corrected', "
            "'validated', 'accepted', 'rejected', 'confirmed_duplicate', 'failed')",
            name="chk_docs_state",
        ),
        sa.CheckConstraint(
            "state != 'failed' OR failure_reason IS NOT NULL",
            name="chk_docs_failure_reason",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_docs_owner", "source_documents", ["owner_id"])
    op.create_index("idx_docs_owner_state", "source_documents", ["owner_id", "state"])
    op.create_index("idx_docs_owner_date", "source_documents", ["owner_id", sa.text("uploaded_at DESC")])
    op.create_unique_index(
        "uq_docs_owner_fingerprint",
        "source_documents",
        ["owner_id", "fingerprint_sha256"],
    )
    op.create_index("idx_docs_dup_key", "source_documents", ["owner_id", "dup_key"])

    # extraction_jobs (work queue, ADR-0005)
    op.create_table(
        "extraction_jobs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_fingerprint", sa.Char(length=64), nullable=False),
        sa.Column("format_detected", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("claimed_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column("extraction_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "format_detected IN ('xml', 'pdf_text', 'pdf_scanned', 'image')",
            name="chk_job_format",
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'running', 'completed', 'failed')",
            name="chk_job_state",
        ),
        sa.CheckConstraint(
            "state != 'failed' OR failure_reason IS NOT NULL",
            name="chk_job_failure_reason",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id"], ["source_documents.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "idx_jobs_claim",
        "extraction_jobs",
        ["state", "next_retry_at"],
        postgresql_where=sa.text("state = 'pending'"),
    )
    op.create_index("idx_jobs_document", "extraction_jobs", ["document_id"])

    # duplications (E15)
    op.create_table(
        "duplications",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_a_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_b_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dup_type", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="probable"),
        sa.Column("resolved_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("dup_type IN ('fingerprint', 'logical')", name="chk_dup_type"),
        sa.CheckConstraint(
            "state IN ('probable', 'confirmed', 'resolved_not_duplicate')",
            name="chk_dup_state",
        ),
        sa.CheckConstraint("document_a_id != document_b_id", name="chk_dup_different_docs"),
        sa.ForeignKeyConstraint(["owner_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_a_id"], ["source_documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_b_id"], ["source_documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_dups_owner", "duplications", ["owner_id", "state"])

    # audit_events (E16, ADR-0012)
    op.create_table(
        "audit_events",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("actor", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("before_data", postgresql.JSONB, nullable=True),
        sa.Column("after_data", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["owner_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_audit_entity", "audit_events", ["owner_id", "entity_type", "entity_id"])
    op.create_index("idx_audit_actor", "audit_events", ["actor"])

    # Append-only trigger for audit_events (ADR-0012)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_update()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only: UPDATE not allowed';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_delete()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only: DELETE not allowed';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_no_update
        BEFORE UPDATE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_update();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_no_delete
        BEFORE DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_delete();
        """
    )

    # idempotency_keys (NFR-4)
    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["owner_id"], ["organizations.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_idem_owner", "idempotency_keys", ["owner_id"])


def downgrade() -> None:
    op.drop_index("idx_idem_owner", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")

    op.execute("DROP TRIGGER IF EXISTS trg_audit_no_delete ON audit_events")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_no_update ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_delete()")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_update()")
    op.drop_index("idx_audit_actor", table_name="audit_events")
    op.drop_index("idx_audit_entity", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("idx_dups_owner", table_name="duplications")
    op.drop_table("duplications")

    op.drop_index("idx_jobs_document", table_name="extraction_jobs")
    op.drop_index("idx_jobs_claim", table_name="extraction_jobs")
    op.drop_table("extraction_jobs")

    op.drop_index("idx_docs_dup_key", table_name="source_documents")
    op.drop_index("uq_docs_owner_fingerprint", table_name="source_documents")
    op.drop_index("idx_docs_owner_date", table_name="source_documents")
    op.drop_index("idx_docs_owner_state", table_name="source_documents")
    op.drop_index("idx_docs_owner", table_name="source_documents")
    op.drop_table("source_documents")
