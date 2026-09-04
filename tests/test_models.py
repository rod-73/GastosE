"""Tests for model constraints and invariants."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import exc
from sqlalchemy.orm import Session as DbSession

from backend.models import (
    Organization,
    User,
    SourceDocument,
    ExtractionJob,
    Duplication,
)


@pytest.mark.skip(reason="CHECK constraints are enforced by PostgreSQL, not SQLite")
def test_organization_state_constraint(db_session: DbSession):
    """Organization state must be 'active' or 'inactive' (PostgreSQL CHECK)."""
    org = Organization(
        id=uuid.uuid4(),
        name="Test Org",
        state="invalid_state",
    )
    db_session.add(org)
    with pytest.raises(exc.IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.skip(reason="CHECK constraints are enforced by PostgreSQL, not SQLite")
def test_user_role_constraint(db_session: DbSession, test_org):
    """User role must be one of the valid roles (PostgreSQL CHECK)."""
    user = User(
        id=uuid.uuid4(),
        organization_id=test_org.id,
        username="testuser2",
        email="test2@example.com",
        password_hash="hashed",
        role="invalid_role",
        state="active",
    )
    db_session.add(user)
    with pytest.raises(exc.IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_source_document_failed_requires_failure_reason(db_session: DbSession, test_org, test_user):
    """SourceDocument in 'failed' state must have failure_reason (INV-15)."""
    doc = SourceDocument(
        id=uuid.uuid4(),
        owner_id=test_org.id,
        safe_name="test.pdf",
        fingerprint_sha256="a" * 64,
        doc_type="other",
        format_detected="pdf_text",
        size_bytes=100,
        uploaded_by=test_user.id,
        state="failed",
        failure_reason=None,  # Should violate the constraint
    )
    db_session.add(doc)
    with pytest.raises(exc.IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_source_document_failed_with_reason_ok(db_session: DbSession, test_org, test_user):
    """SourceDocument in 'failed' state with failure_reason is valid."""
    doc = SourceDocument(
        id=uuid.uuid4(),
        owner_id=test_org.id,
        safe_name="test.pdf",
        fingerprint_sha256="b" * 64,
        doc_type="other",
        format_detected="pdf_text",
        size_bytes=100,
        uploaded_by=test_user.id,
        state="failed",
        failure_reason="Something went wrong",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    assert doc.state == "failed"
    assert doc.failure_reason == "Something went wrong"


def test_extraction_job_failed_requires_failure_reason(db_session: DbSession, test_org, test_user):
    """ExtractionJob in 'failed' state must have failure_reason."""
    doc = SourceDocument(
        id=uuid.uuid4(),
        owner_id=test_org.id,
        safe_name="test.pdf",
        fingerprint_sha256="c" * 64,
        doc_type="other",
        format_detected="pdf_text",
        size_bytes=100,
        uploaded_by=test_user.id,
        state="uploaded",
    )
    db_session.add(doc)
    db_session.commit()

    job = ExtractionJob(
        id=uuid.uuid4(),
        owner_id=test_org.id,
        document_id=doc.id,
        document_fingerprint="c" * 64,
        format_detected="pdf_text",
        state="failed",
        failure_reason=None,  # Should violate the constraint
    )
    db_session.add(job)
    with pytest.raises(exc.IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_duplication_different_documents_constraint(db_session: DbSession, test_org, test_user):
    """Duplication must reference two different documents."""
    doc1 = SourceDocument(
        id=uuid.uuid4(),
        owner_id=test_org.id,
        safe_name="test1.pdf",
        fingerprint_sha256="d" * 64,
        doc_type="other",
        format_detected="pdf_text",
        size_bytes=100,
        uploaded_by=test_user.id,
        state="uploaded",
    )
    db_session.add(doc1)
    db_session.commit()

    dup = Duplication(
        id=uuid.uuid4(),
        owner_id=test_org.id,
        document_a_id=doc1.id,
        document_b_id=doc1.id,  # Same document - should violate constraint
        dup_type="fingerprint",
        state="probable",
    )
    db_session.add(dup)
    with pytest.raises(exc.IntegrityError):
        db_session.commit()
    db_session.rollback()
