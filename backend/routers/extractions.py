"""Extraction endpoints (V2-S2): retry, list, detail.

- POST /api/v1/documents/{id}/extractions/retry: create a new extraction
  job if the previous failure is recoverable (FR-FST-2).
- GET /api/v1/documents/{id}/extractions: list extractions for a document.
- GET /api/v1/extractions/{id}: get a specific extraction with its values.
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from backend.database import get_db
from backend.exceptions import ConflictException, NotFoundException
from backend.middleware.auth import get_session, require_role
from backend.models.document import SourceDocument
from backend.models.extraction import Extraction, ExtractedValue
from backend.models.extraction_job import ExtractionJob
from backend.models.session import Session
from backend.utils import uuid7

router = APIRouter(tags=["extractions"])


# --- Schemas ---


class ExtractionValueResponse(BaseModel):
    """A single extracted value with confidence and provenance."""

    id: uuid.UUID
    field: str
    raw_value: str
    confidence: float
    provenance: dict
    created_at: str


class ExtractionResponse(BaseModel):
    """Extraction detail with its values."""

    id: uuid.UUID
    document_id: uuid.UUID
    method: str
    state: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    failure_reason: Optional[str] = None
    created_at: str
    updated_at: str
    values: List[ExtractionValueResponse] = []


class ExtractionListResponse(BaseModel):
    """List of extractions for a document."""

    document_id: uuid.UUID
    count: int
    extractions: List[ExtractionResponse]


class RetryResponse(BaseModel):
    """Response for a retry request."""

    job_id: uuid.UUID
    document_id: uuid.UUID
    state: str
    message: str


# --- Endpoints ---


@router.post(
    "/api/v1/documents/{document_id}/extractions/retry",
    response_model=RetryResponse,
    dependencies=[Depends(require_role("reader"))],
)
def retry_extraction(
    document_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> RetryResponse:
    """Create a new extraction job for a document whose extraction failed.

    Conditions:
    - The document must exist and belong to the caller's org.
    - The document state must be 'failed' (permanent extraction failure).
    - No pending/running jobs should exist for this document.

    Creates a new ExtractionJob in 'pending' state and resets the
    document state to 'uploaded' (ready for re-processing).
    """
    # Verify document exists and belongs to the caller.
    document = (
        db.execute(
            select(SourceDocument).where(
                SourceDocument.id == document_id,
                SourceDocument.owner_id == session.organization_id,
            )
        )
        .scalars()
        .first()
    )
    if document is None:
        raise NotFoundException("Document")

    # Check that the document is in a failed state.
    if document.state != "failed":
        raise ConflictException(
            "Document is not in a failed state "
            f"(current: {document.state}). Retry is only available "
            "after a permanent extraction failure."
        )

    # Check for existing pending/running jobs.
    active_job = (
        db.execute(
            select(ExtractionJob).where(
                ExtractionJob.document_id == document_id,
                ExtractionJob.state.in_(["pending", "running"]),
            )
        )
        .scalars()
        .first()
    )
    if active_job is not None:
        raise ConflictException(
            "An active extraction job already exists for this document."
        )

    # Create a new job.
    job = ExtractionJob(
        id=uuid7(),
        owner_id=session.organization_id,
        document_id=document_id,
        document_fingerprint=document.fingerprint_sha256,
        format_detected=document.format_detected,
        state="pending",
    )
    db.add(job)

    # Reset document state.
    document.state = "uploaded"
    document.failure_reason = None

    db.commit()
    db.refresh(job)

    return RetryResponse(
        job_id=job.id,
        document_id=document_id,
        state="pending",
        message="Extraction retry scheduled. The document will be re-processed.",
    )


@router.get(
    "/api/v1/documents/{document_id}/extractions",
    response_model=ExtractionListResponse,
    dependencies=[Depends(require_role("reader"))],
)
def list_extractions(
    document_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> ExtractionListResponse:
    """List all extractions for a document (newest first)."""
    # Verify document exists and belongs to the caller.
    document = (
        db.execute(
            select(SourceDocument).where(
                SourceDocument.id == document_id,
                SourceDocument.owner_id == session.organization_id,
            )
        )
        .scalars()
        .first()
    )
    if document is None:
        raise NotFoundException("Document")

    extractions = (
        db.execute(
            select(Extraction)
            .where(
                Extraction.document_id == document_id,
                Extraction.owner_id == session.organization_id,
            )
            .order_by(Extraction.created_at.desc())
        )
        .scalars()
        .all()
    )

    items = [_extraction_to_response(ext, db) for ext in extractions]

    return ExtractionListResponse(
        document_id=document_id,
        count=len(items),
        extractions=items,
    )


@router.get(
    "/api/v1/extractions/{extraction_id}",
    response_model=ExtractionResponse,
    dependencies=[Depends(require_role("reader"))],
)
def get_extraction(
    extraction_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> ExtractionResponse:
    """Get a specific extraction with its extracted values."""
    extraction = (
        db.execute(
            select(Extraction).where(
                Extraction.id == extraction_id,
                Extraction.owner_id == session.organization_id,
            )
        )
        .scalars()
        .first()
    )
    if extraction is None:
        raise NotFoundException("Extraction")

    return _extraction_to_response(extraction, db)


# --- Helpers ---


def _extraction_to_response(
    extraction: Extraction, db: DbSession
) -> ExtractionResponse:
    """Convert an Extraction ORM object to the API response schema."""
    values = (
        db.execute(
            select(ExtractedValue)
            .where(ExtractedValue.extraction_id == extraction.id)
            .order_by(ExtractedValue.field.asc())
        )
        .scalars()
        .all()
    )

    return ExtractionResponse(
        id=extraction.id,
        document_id=extraction.document_id,
        method=extraction.method,
        state=extraction.state,
        started_at=extraction.started_at.isoformat() if extraction.started_at else None,
        finished_at=extraction.finished_at.isoformat() if extraction.finished_at else None,
        failure_reason=extraction.failure_reason,
        created_at=extraction.created_at.isoformat() if extraction.created_at else "",
        updated_at=extraction.updated_at.isoformat() if extraction.updated_at else "",
        values=[
            ExtractionValueResponse(
                id=v.id,
                field=v.field,
                raw_value=v.raw_value,
                confidence=float(v.confidence),
                provenance=v.provenance,
                created_at=v.created_at.isoformat() if v.created_at else "",
            )
            for v in values
        ],
    )
