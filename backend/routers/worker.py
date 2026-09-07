"""Worker endpoints (V2-S1): claim, process, reap.

These endpoints are used by the extraction worker process to:
- Claim a pending job (atomic, FIFO).
- Process the claimed job (extract, validate, persist).
- Reap expired leases (worker crash recovery).

Authentication: the worker authenticates with a valid session token
(like any other API consumer). The worker_id is derived from the session.
"""
import uuid
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from backend.database import get_db
from backend.middleware.auth import get_session, require_role
from backend.models.extraction import Extraction, ExtractedValue
from backend.models.extraction_job import ExtractionJob
from backend.models.session import Session
from backend.services import extraction_service

router = APIRouter(prefix="/api/v1/worker", tags=["worker"])


class WorkerClaimResponse(BaseModel):
    """Response for claiming a job."""

    job_id: UUID
    document_id: UUID
    format_detected: str
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    attempts: int
    max_attempts: int


class WorkerProcessResponse(BaseModel):
    """Response for processing a job."""

    job_id: UUID
    extraction_id: Optional[UUID] = None
    state: str
    method: str
    fields_extracted: int
    failure_code: Optional[str] = None
    failure_reason: Optional[str] = None


class WorkerReapResponse(BaseModel):
    """Response for reaping expired leases."""

    reaped_count: int


@router.post(
    "/claim",
    response_model=WorkerClaimResponse,
    dependencies=[Depends(require_role("reader"))],
)
def claim_job(
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> WorkerClaimResponse:
    """Atomically claim the next pending extraction job.

    The worker_id is the session's user_id. Returns 404
    if no pending jobs exist for the caller's organization.
    """
    worker_id = session.user_id
    owner_id = session.organization_id
    job = extraction_service.claim_job(worker_id, owner_id, db)

    if job is None:
        # No pending jobs: return 404.
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No pending jobs")

    return WorkerClaimResponse(
        job_id=job.id,
        document_id=job.document_id,
        format_detected=job.format_detected,
        fingerprint=job.document_fingerprint,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
    )


@router.post(
    "/process",
    response_model=WorkerProcessResponse,
    dependencies=[Depends(require_role("reader"))],
)
def process_job(
    job_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> WorkerProcessResponse:
    """Process a claimed extraction job.

    The job must be in 'running' state and claimed by this worker.
    """
    job = (
        db.execute(
            select(ExtractionJob).where(
                ExtractionJob.id == job_id,
                ExtractionJob.owner_id == session.organization_id,
            )
        )
        .scalars()
        .first()
    )
    if job is None:
        from backend.exceptions import NotFoundException
        raise NotFoundException("Extraction job")

    if job.state != "running":
        from backend.exceptions import GastosEException
        raise GastosEException(
            "job.not_running",
            f"Job is not in 'running' state (current: {job.state})",
            409,
        )

    if job.claimed_by != session.user_id:
        from backend.exceptions import ForbiddenException
        raise ForbiddenException()

    extraction = extraction_service.process_job(job, db)

    # If extraction is None, the job failed (no Extraction record created).
    if extraction is None:
        return WorkerProcessResponse(
            job_id=job.id,
            extraction_id=job.extraction_id,
            state="failed",
            method=job.format_detected,
            fields_extracted=0,
            failure_code=job.failure_code,
            failure_reason=job.failure_reason,
        )

    # Count fields.
    from backend.models.extraction import ExtractedValue
    field_count = (
        db.execute(
            select(ExtractedValue).where(
                ExtractedValue.extraction_id == extraction.id,
            )
        )
        .scalars()
        .all()
    )

    return WorkerProcessResponse(
        job_id=job.id,
        extraction_id=extraction.id,
        state=extraction.state,
        method=extraction.method,
        fields_extracted=len(field_count),
        failure_code=job.failure_code,
        failure_reason=job.failure_reason,
    )


@router.post(
    "/reap",
    response_model=WorkerReapResponse,
    dependencies=[Depends(require_role("reader"))],
)
def reap_expired(
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> WorkerReapResponse:
    """Reap jobs with expired leases (worker crash recovery)."""
    count = extraction_service.reap_expired_leases(db)
    return WorkerReapResponse(reaped_count=count)
