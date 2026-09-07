"""Document ingestion service (V1-S1).

Implements the upload pipeline: size validation, magic-byte format
detection, SHA-256 fingerprint, safe-name generation, duplicate
detection, filesystem storage, and DB records (SourceDocument +
ExtractionJob + AuditEvent).

After upload, the extraction job is processed synchronously in the
same request (no separate worker process).
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from typing import Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from backend.config import get_settings
from backend.exceptions import (
    DocumentTooLargeException,
    DuplicateDocumentException,
    UnsupportedFormatException,
)
from backend.models.audit_event import AuditEvent
from backend.models.document import SourceDocument
from backend.models.extraction_job import ExtractionJob
from backend.models.session import Session
from backend.services import extraction_service
from backend.utils import uuid7

logger = logging.getLogger(__name__)

# Magic-byte signatures (checked in order; first match wins).
_MAGIC_SIGNATURES: list[Tuple[bytes, str, str]] = [
    (b"%PDF-", "pdf", "pdf_text"),
    (b"<?xml", "xml", "xml"),
    (b"\xff\xd8\xff", "jpg", "image"),
    (b"\x89PNG", "png", "image"),
]


def detect_format(content: bytes) -> Tuple[str, str]:
    """Detect document format from magic bytes.

    Returns ``(extension, format_detected)``. Raises
    ``UnsupportedFormatException`` when no signature matches.
    """
    for signature, extension, fmt in _MAGIC_SIGNATURES:
        if content.startswith(signature):
            return extension, fmt
    raise UnsupportedFormatException()


def calculate_fingerprint(content: bytes) -> str:
    """Return the SHA-256 hex digest of ``content``."""
    return hashlib.sha256(content).hexdigest()


def _generate_safe_name(extension: str) -> str:
    """Generate a safe filename: ``<uuid7>.<ext>`` (ADR-0006)."""
    return f"{uuid7()}.{extension}"


def _store_file(
    owner_id: uuid.UUID,
    fingerprint: str,
    content: bytes,
) -> str:
    """Write the file to ``{DOCUMENT_STORAGE_PATH}/{owner_id}/{fingerprint}``.

    Returns the absolute path. Directories are created as needed.
    """
    settings = get_settings()
    directory = os.path.join(settings.DOCUMENT_STORAGE_PATH, str(owner_id))
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, fingerprint)
    with open(path, "wb") as fh:
        fh.write(content)
    return path


def _find_existing_document(
    db: DbSession,
    owner_id: uuid.UUID,
    fingerprint: str,
) -> Optional[SourceDocument]:
    """Return the existing document with the same (owner, fingerprint)."""
    return (
        db.execute(
            select(SourceDocument).where(
                SourceDocument.owner_id == owner_id,
                SourceDocument.fingerprint_sha256 == fingerprint,
            )
        )
        .scalars()
        .first()
    )


def upload_document(
    file_content: bytes,
    original_filename: str,
    session: Session,
    db: DbSession,
) -> SourceDocument:
    """Upload a source document (V1-S1 pipeline).

    Steps:
      1. Validate size (<= MAX_UPLOAD_SIZE).
      2. Detect format via magic bytes.
      3. Calculate SHA-256 fingerprint.
      4. Generate safe name.
      5. Check for duplicate (same owner + fingerprint).
      6. If duplicate: create Duplication record, return existing document.
      7. Store file in filesystem.
      8. Create SourceDocument (state='uploaded').
      9. Create ExtractionJob (state='pending').
     10. Create AuditEvent.
     11. Return document.
    """
    settings = get_settings()

    # 1. Size validation.
    if len(file_content) > settings.MAX_UPLOAD_SIZE:
        raise DocumentTooLargeException()

    # 2. Format detection.
    extension, format_detected = detect_format(file_content)

    # 3. Fingerprint.
    fingerprint = calculate_fingerprint(file_content)

    # 4. Safe name.
    safe_name = _generate_safe_name(extension)

    owner_id = session.organization_id

    # 5/6. Duplicate check.
    #
    # The ``duplications`` table requires ``document_a_id != document_b_id``
    # (CHECK constraint), so a re-upload of the *exact same file* (same
    # fingerprint) cannot be recorded as a self-duplication. Per the V1-S1
    # spec we raise 409 with the existing document id; the caller can then
    # ``GET /documents/{existing_id}`` to inspect it.
    existing = _find_existing_document(db, owner_id, fingerprint)
    if existing is not None:
        raise DuplicateDocumentException(existing_id=str(existing.id))

    # 7. Store file.
    _store_file(owner_id, fingerprint, file_content)

    # 8. SourceDocument.
    document = SourceDocument(
        id=uuid7(),
        owner_id=owner_id,
        safe_name=safe_name,
        original_filename=original_filename,
        fingerprint_sha256=fingerprint,
        doc_type="other",  # auto-detection out of scope for V1-S1
        format_detected=format_detected,
        size_bytes=len(file_content),
        page_count=None,
        uploaded_by=session.user_id,
        state="uploaded",
    )
    db.add(document)
    db.flush()  # assign server-side defaults / obtain id

    # 9. ExtractionJob.
    job = ExtractionJob(
        id=uuid7(),
        owner_id=owner_id,
        document_id=document.id,
        document_fingerprint=fingerprint,
        format_detected=format_detected,
        state="pending",
    )
    db.add(job)

    # 10. AuditEvent.
    audit = AuditEvent(
        id=uuid7(),
        owner_id=owner_id,
        entity_type="source_document",
        entity_id=document.id,
        action="document.uploaded",
        actor=session.user_id,
        after_data={
            "safe_name": safe_name,
            "fingerprint_sha256": fingerprint,
            "format_detected": format_detected,
            "size_bytes": len(file_content),
        },
    )
    db.add(audit)

    db.commit()
    db.refresh(document)

    # 11. Process extraction synchronously.
    # Extraction failures are non-fatal: the document remains uploaded
    # and the job is marked as failed. The user can retry later.
    extraction_id = None
    try:
        # Process the job directly (sets state to 'running', then processes).
        extraction_service.process_job_direct(job, db, actor_id=session.user_id)
        extraction = extraction_service.process_job(job, db)
        if extraction is not None:
            extraction_id = extraction.id
            logger.info(
                "Extraction completed for document %s (job %s, extraction %s)",
                document.id,
                job.id,
                extraction_id,
            )
        else:
            logger.warning(
                "Extraction failed for document %s (job %s): %s",
                document.id,
                job.id,
                job.failure_reason,
            )
    except Exception as e:
        logger.error("Extraction failed for document %s: %s", document.id, e)
        # Rollback the failed transaction and mark job as failed.
        db.rollback()
        # Re-fetch the job after rollback.
        job = (
            db.execute(
                select(ExtractionJob).where(ExtractionJob.id == job.id)
            )
            .scalars()
            .first()
        )
        if job:
            job.state = "failed"
            job.failure_code = "extraction_error"
            job.failure_reason = str(e)[:2000]  # Truncate long errors
            db.commit()

    # 12. If extraction succeeded, run normalization, validation, and create expense.
    if extraction_id:
        try:
            from backend.services import normalization_service
            from backend.services import validation_service
            from backend.services import expense_service
            from backend.models.extraction import Extraction

            # Get the extraction.
            extraction = (
                db.execute(
                    select(Extraction).where(Extraction.id == extraction_id)
                )
                .scalars()
                .first()
            )
            if extraction:
                # Step 1: Normalize extracted values.
                normalized_count, norm_failed = normalization_service.normalize_extraction(
                    extraction_id=extraction_id,
                    owner_id=owner_id,
                    db=db,
                )
                logger.info(
                    "Normalization completed: %d normalized, %d failed",
                    normalized_count,
                    norm_failed,
                )

                # Step 2: Validate normalized values.
                passed, failed, warnings = validation_service.validate_extraction(
                    extraction_id=extraction_id,
                    owner_id=owner_id,
                    db=db,
                )
                logger.info(
                    "Validation completed: %d passed, %d failed, %d warnings",
                    passed,
                    failed,
                    warnings,
                )

                # Step 3: If validation passed (no blocking errors), create expense.
                if failed == 0:
                    expense = expense_service.create_expense_from_validation(
                        extraction_id=extraction_id,
                        owner_id=owner_id,
                        db=db,
                    )
                    logger.info(
                        "Expense created: %s (total: %s)",
                        expense.id,
                        expense.total,
                    )
                    # Update document state to 'accepted'.
                    document.state = "accepted"
                    db.commit()
                else:
                    logger.warning(
                        "Validation has %d blocking errors; expense not created",
                        failed,
                    )
        except Exception as e:
            logger.error(
                "Normalization/validation/expense creation failed for document %s: %s",
                document.id,
                e,
            )
            # Non-fatal: document remains in 'extracted' state.
            db.rollback()

    db.refresh(document)
    return document


def verify_fingerprint(
    document_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: DbSession,
) -> bool:
    """Re-read the stored file and compare its SHA-256 with the DB record.

    Returns ``True`` when the fingerprint matches, ``False`` otherwise
    (including when the file is missing).
    """
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
        return False

    settings = get_settings()
    path = os.path.join(
        settings.DOCUMENT_STORAGE_PATH,
        str(owner_id),
        document.fingerprint_sha256,
    )
    if not os.path.isfile(path):
        return False

    sha = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest() == document.fingerprint_sha256


def delete_document(
    document_id: uuid.UUID,
    owner_id: uuid.UUID,
    actor_id: uuid.UUID,
    db: DbSession,
) -> None:
    """Delete a document and all associated data (cascade).

    Deletes in FK dependency order:
    1. audit_events (entity_id = document_id)
    2. duplications (document_a_id or document_b_id)
    3. validated_values -> normalized_values -> extracted_values -> extractions
    4. expense_lines -> expenses
    5. split_expenses -> document_splits
    6. extraction_jobs
    7. source_documents
    8. File on storage

    Raises NotFoundException if the document does not exist or belongs
    to a different organization.
    """
    from backend.models.audit_event import AuditEvent
    from backend.models.duplication import Duplication
    from backend.models.extraction import Extraction, ExtractedValue
    from backend.models.extraction_job import ExtractionJob
    from backend.models.expense import Expense, ExpenseLine
    from backend.models.normalized_value import NormalizedValue
    from backend.models.validated_value import ValidatedValue
    from backend.models.document_split import DocumentSplit, SplitExpense
    from backend.utils import uuid7
    from datetime import datetime, timezone

    # Verify document exists and belongs to the caller's org.
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
        from backend.exceptions import NotFoundException
        raise NotFoundException("Document")

    # NOTE: audit_events is append-only (PostgreSQL trigger prevents DELETE).
    # We do NOT delete audit events. The deletion is recorded via a new
    # audit event at the end of this function.

    # 1. Delete duplications involving this document.
    db.execute(
        delete(Duplication).where(
            (Duplication.document_a_id == document_id) |
            (Duplication.document_b_id == document_id),
            Duplication.owner_id == owner_id,
        )
    )

    # 2. Delete extraction chain: validated -> normalized -> extracted -> extractions.
    # Get extraction IDs for this document.
    extraction_ids = (
        db.execute(
            select(Extraction.id).where(
                Extraction.document_id == document_id,
                Extraction.owner_id == owner_id,
            )
        )
        .scalars()
        .all()
    )

    if extraction_ids:
        # Delete validated_values (via normalized_values -> extracted_values).
        # First get normalized_value IDs linked to extracted_values of these extractions.
        extracted_value_ids = (
            db.execute(
                select(ExtractedValue.id).where(
                    ExtractedValue.extraction_id.in_(extraction_ids),
                )
            )
            .scalars()
            .all()
        )
        if extracted_value_ids:
            normalized_value_ids = (
                db.execute(
                    select(NormalizedValue.id).where(
                        NormalizedValue.extracted_value_id.in_(extracted_value_ids),
                    )
                )
                .scalars()
                .all()
            )
            if normalized_value_ids:
                db.execute(
                    delete(ValidatedValue).where(
                        ValidatedValue.normalized_value_id.in_(normalized_value_ids),
                    )
                )
            db.execute(
                delete(NormalizedValue).where(
                    NormalizedValue.extracted_value_id.in_(extracted_value_ids),
                )
            )
        db.execute(
            delete(ExtractedValue).where(
                ExtractedValue.extraction_id.in_(extraction_ids),
            )
        )

    db.execute(
        delete(Extraction).where(
            Extraction.document_id == document_id,
            Extraction.owner_id == owner_id,
        )
    )

    # 3. Delete expenses and all dependent records for this document.
    expense_ids = (
        db.execute(
            select(Expense.id).where(
                Expense.document_id == document_id,
                Expense.owner_id == owner_id,
            )
        )
        .scalars()
        .all()
    )
    if expense_ids:
        # 3a. tax_lines (references expense_lines and expenses).
        from backend.models.expense import TaxLine
        db.execute(
            delete(TaxLine).where(
                (TaxLine.expense_id.in_(expense_ids)) |
                (TaxLine.expense_line_id.in_(
                    select(ExpenseLine.id).where(
                        ExpenseLine.expense_id.in_(expense_ids),
                    )
                )),
            )
        )
        # 3b. manual_corrections (references expenses).
        from backend.models.manual_correction import ManualCorrection
        db.execute(
            delete(ManualCorrection).where(
                ManualCorrection.expense_id.in_(expense_ids),
            )
        )
        # 3c. payments (references expenses).
        from backend.models.payment import Payment
        db.execute(
            delete(Payment).where(
                Payment.expense_id.in_(expense_ids),
            )
        )
        # 3d. split_expenses (references expenses).
        db.execute(
            delete(SplitExpense).where(
                SplitExpense.expense_id.in_(expense_ids),
            )
        )
        # 3e. expense_lines.
        db.execute(
            delete(ExpenseLine).where(
                ExpenseLine.expense_id.in_(expense_ids),
            )
        )
        # 3f. expenses.
        db.execute(
            delete(Expense).where(
                Expense.id.in_(expense_ids),
            )
        )

    # 4. Delete document_splits for this document.
    split_ids = (
        db.execute(
            select(DocumentSplit.id).where(
                DocumentSplit.document_id == document_id,
                DocumentSplit.owner_id == owner_id,
            )
        )
        .scalars()
        .all()
    )
    if split_ids:
        db.execute(
            delete(SplitExpense).where(
                SplitExpense.split_id.in_(split_ids),
            )
        )
        db.execute(
            delete(DocumentSplit).where(
                DocumentSplit.id.in_(split_ids),
            )
        )

    # 5. Delete extraction jobs.
    db.execute(
        delete(ExtractionJob).where(
            ExtractionJob.document_id == document_id,
            ExtractionJob.owner_id == owner_id,
        )
    )

    # 6. Delete the source document.
    db.delete(document)

    # 7. Delete the file from storage.
    settings = get_settings()
    path = os.path.join(
        settings.DOCUMENT_STORAGE_PATH,
        str(owner_id),
        document.fingerprint_sha256,
    )
    if os.path.isfile(path):
        os.remove(path)

    # Audit event for the deletion.
    audit = AuditEvent(
        id=uuid7(),
        owner_id=owner_id,
        entity_type="source_document",
        entity_id=document_id,
        action="document.deleted",
        actor=actor_id,
        after_data={
            "safe_name": document.safe_name,
            "fingerprint_sha256": document.fingerprint_sha256,
        },
    )
    db.add(audit)

    db.commit()
    logger.info(
        "Document %s deleted (owner=%s, actor=%s)",
        document_id, owner_id, actor_id,
    )
