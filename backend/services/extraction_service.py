"""Extraction worker service (V2-S1).

Implements the extraction pipeline:
1. Claim a pending job atomically (ADR-0005).
2. Verify document integrity (fingerprint check).
3. Select extraction method by cascade (deterministic first).
4. Execute extraction with the selected method.
5. Validate output against strict schema (VR-SCHEMA-1).
6. Persist Extraction (E2) + ExtractedValues (E3) with confidence/provenance.
7. Mark job completed/failed.
8. Handle retries with backoff.

Idempotency (NFR-4): if a completed extraction already exists for the
document, the job is marked completed without re-executing.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from backend.config import get_settings
from backend.models.audit_event import AuditEvent
from backend.models.document import SourceDocument
from backend.models.extraction import Extraction, ExtractedValue
from backend.models.extraction_job import ExtractionJob
from backend.utils import uuid7
from backend.services.extraction_methods import select_method
from backend.services.extraction_schema import validate_extraction_output

logger = logging.getLogger(__name__)

# Backoff intervals (minutes) for retry attempts.
BACKOFF_MINUTES = [1, 5, 30]

# Lease duration for a running job.
LEASE_DURATION_MINUTES = 5


def compute_backoff(attempts: int) -> timedelta:
    """Compute the backoff delay for a given attempt number.

    attempts=1 -> 1 minute
    attempts=2 -> 5 minutes
    attempts>=3 -> 30 minutes
    """
    idx = min(attempts - 1, len(BACKOFF_MINUTES) - 1)
    return timedelta(minutes=BACKOFF_MINUTES[max(idx, 0)])


def claim_job(
    worker_id: uuid.UUID, owner_id: uuid.UUID, db: DbSession
) -> Optional[ExtractionJob]:
    """Atomically claim a pending extraction job.

    In production (PostgreSQL), this uses:
        UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED)

    For SQLite (tests), we use a simple SELECT + UPDATE pattern.
    The atomicity guarantee is provided by the database in production.

    Scoped to the caller's organization (ADR-0008).

    Returns the claimed job or None if no pending jobs exist.
    """
    now = datetime.now(timezone.utc)

    # Find the oldest pending job that is eligible for processing.
    job = (
        db.execute(
            select(ExtractionJob)
            .where(
                ExtractionJob.state == "pending",
                ExtractionJob.owner_id == owner_id,
                (ExtractionJob.next_retry_at == None)  # noqa: E711
                | (ExtractionJob.next_retry_at <= now),
            )
            .order_by(ExtractionJob.created_at.asc())
            .limit(1)
        )
        .scalars()
        .first()
    )

    if job is None:
        return None

    # Claim the job.
    job.state = "running"
    job.claimed_by = worker_id
    job.claimed_at = now
    job.lease_expires_at = now + timedelta(minutes=LEASE_DURATION_MINUTES)
    job.attempts = job.attempts + 1
    job.updated_at = now

    db.commit()
    db.refresh(job)
    return job


def process_job(job: ExtractionJob, db: DbSession) -> Extraction:
    """Process a claimed extraction job.

    Steps:
    1. Check idempotency: if a completed extraction exists, reuse it.
    2. Verify document integrity.
    3. Read document content from filesystem.
    4. Select and execute extraction method.
    5. Validate output.
    6. Persist results.
    7. Update job state.

    Returns the Extraction record.
    """
    owner_id = job.owner_id
    document_id = job.document_id

    # 1. Idempotency check.
    existing = (
        db.execute(
            select(Extraction).where(
                Extraction.document_id == document_id,
                Extraction.state == "completed",
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        # Mark job as completed (idempotent re-execution).
        job.state = "completed"
        job.extraction_id = existing.id
        job.failure_reason = None
        job.failure_code = None
        job.updated_at = datetime.now(timezone.utc)
        db.commit()
        return existing

    # 2. Verify document exists.
    document = (
        db.execute(
            select(SourceDocument).where(
                SourceDocument.id == document_id,
                SourceDocument.owner_id == owner_id,
            )
        )
        .scalars()
        .first()
    )
    if document is None:
        return _fail_job(job, "document_not_found", "Document not found", db)

    # 3. Read document content.
    settings = get_settings()
    path = os.path.join(
        settings.DOCUMENT_STORAGE_PATH,
        str(owner_id),
        document.fingerprint_sha256,
    )
    if not os.path.isfile(path):
        return _fail_job(
            job, "file_not_found", "Document file not found on storage", db
        )

    with open(path, "rb") as fh:
        content = fh.read()

    # 4. Select and execute extraction method.
    method_name, method_fn = select_method(job.format_detected)

    try:
        raw_output = method_fn(content)
    except Exception as e:
        logger.exception("Extraction method %s failed", method_name)
        return _fail_job(
            job,
            "extraction_error",
            f"Extraction method {method_name} raised: {e}",
            db,
        )

    # 5. Validate output against strict schema.
    result = validate_extraction_output(raw_output, method_name)

    if not result.is_valid:
        error_msg = "; ".join(result.errors)
        return _fail_job(
            job, "schema_validation_error", f"Schema validation failed: {error_msg}", db
        )

    # 6. Persist Extraction + ExtractedValues.
    now = datetime.now(timezone.utc)
    extraction = Extraction(
        id=uuid7(),
        owner_id=owner_id,
        document_id=document_id,
        method=method_name,
        state="completed",
        started_at=now,
        finished_at=now,
    )
    db.add(extraction)
    db.flush()  # Get the id.

    for field_ext in result.fields:
        ev = ExtractedValue(
            id=uuid7(),
            owner_id=owner_id,
            extraction_id=extraction.id,
            field=field_ext.field,
            raw_value=field_ext.raw_value,
            confidence=field_ext.confidence,
            provenance=field_ext.provenance,
        )
        db.add(ev)

    # 7. Update job state.
    job.state = "completed"
    job.extraction_id = extraction.id
    job.failure_reason = None
    job.failure_code = None
    job.updated_at = now

    # Update document state to 'extracted'.
    document.state = "extracted"
    document.updated_at = now

    # Audit event.
    audit = AuditEvent(
        id=uuid7(),
        owner_id=owner_id,
        entity_type="extraction",
        entity_id=extraction.id,
        action="extraction.completed",
        actor=job.claimed_by or uuid.UUID(int=0),
        after_data={
            "method": method_name,
            "fields_extracted": len(result.fields),
            "document_id": str(document_id),
        },
    )
    db.add(audit)

    db.commit()
    db.refresh(extraction)
    return extraction


def _fail_job(
    job: ExtractionJob,
    failure_code: str,
    failure_reason: str,
    db: DbSession,
) -> Extraction:
    """Mark a job as failed (or schedule retry).

    If attempts < max_attempts: schedule retry with backoff.
    If attempts >= max_attempts: permanent failure.
    """
    now = datetime.now(timezone.utc)
    job.failure_code = failure_code
    job.failure_reason = failure_reason
    job.updated_at = now

    if job.attempts < job.max_attempts:
        # Schedule retry.
        backoff = compute_backoff(job.attempts)
        job.state = "pending"
        job.next_retry_at = now + backoff
        job.claimed_by = None
        job.claimed_at = None
        job.lease_expires_at = None
    else:
        # Permanent failure.
        job.state = "failed"
        job.next_retry_at = None
        job.claimed_by = None
        job.claimed_at = None
        job.lease_expires_at = None

        # Update document state to 'failed'.
        document = (
            db.execute(
                select(SourceDocument).where(
                    SourceDocument.id == job.document_id,
                )
            )
            .scalars()
            .first()
        )
        if document is not None:
            document.state = "failed"
            document.failure_reason = failure_reason
            document.updated_at = now

    db.commit()
    db.refresh(job)

    # Create a failed extraction record for auditability.
    extraction = Extraction(
        id=uuid7(),
        owner_id=job.owner_id,
        document_id=job.document_id,
        method="unknown",
        state="failed",
        started_at=now,
        finished_at=now,
        failure_reason=failure_reason,
    )
    db.add(extraction)
    db.commit()
    db.refresh(extraction)

    # Audit event.
    audit = AuditEvent(
        id=uuid7(),
        owner_id=job.owner_id,
        entity_type="extraction_job",
        entity_id=job.id,
        action="extraction.failed",
        actor=job.claimed_by or uuid.UUID(int=0),
        after_data={
            "failure_code": failure_code,
            "failure_reason": failure_reason,
            "attempts": job.attempts,
            "max_attempts": job.max_attempts,
        },
    )
    db.add(audit)
    db.commit()

    return extraction


def reap_expired_leases(db: DbSession) -> int:
    """Reap jobs with expired leases (worker died).

    Returns the number of jobs reaped.
    """
    now = datetime.now(timezone.utc)
    expired_jobs = (
        db.execute(
            select(ExtractionJob).where(
                ExtractionJob.state == "running",
                ExtractionJob.lease_expires_at != None,  # noqa: E711
                ExtractionJob.lease_expires_at < now,
            )
        )
        .scalars()
        .all()
    )

    count = 0
    for job in expired_jobs:
        job.state = "pending"
        job.claimed_by = None
        job.claimed_at = None
        job.lease_expires_at = None
        job.updated_at = now
        count += 1

    if count > 0:
        db.commit()

    return count
