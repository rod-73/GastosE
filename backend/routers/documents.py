"""Document endpoints (V1-S1 + V1-S2): upload, retrieve, verify, download."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from backend.config import get_settings
from backend.database import get_db
from backend.exceptions import NotFoundException
from backend.middleware.auth import get_session, require_role
from backend.models.idempotency_key import IdempotencyKey
from backend.models.session import Session
from backend.models.document import SourceDocument
from backend.schemas.document import (
    DocumentDeleteResponse,
    DocumentResponse,
    DocumentUploadResponse,
    FingerprintVerifyResponse,
)
from backend.services import document_service

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

ENDPOINT_UPLOAD = "POST /api/v1/documents"


def _request_hash(file_content: bytes, document_type: Optional[str]) -> str:
    """Stable hash of the request payload (file + declared type)."""
    h = hashlib.sha256()
    h.update(file_content)
    h.update(b"|")
    h.update((document_type or "").encode("utf-8"))
    return h.hexdigest()


@router.post(
    "",
    status_code=202,
    response_model=DocumentUploadResponse,
    dependencies=[Depends(require_role("reader"))],
)
async def upload_document(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    document_type: Optional[str] = Form(default=None),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> DocumentUploadResponse:
    """Upload a source document (asynchronous; 202 + Location).

    Accepts multipart form data with a ``file`` field and an optional
    ``document_type``. Supports the ``Idempotency-Key`` header (NFR-4).
    """
    file_content = await file.read()
    original_filename = file.filename or ""

    # Idempotency: replay a stored response when the same key+payload
    # arrives again for the same owner/endpoint.
    if idempotency_key:
        req_hash = _request_hash(file_content, document_type)
        stored = (
            db.execute(
                select(IdempotencyKey).where(
                    IdempotencyKey.key == idempotency_key,
                    IdempotencyKey.owner_id == session.organization_id,
                    IdempotencyKey.endpoint == ENDPOINT_UPLOAD,
                )
            )
            .scalars()
            .first()
        )
        if stored is not None and stored.request_hash == req_hash:
            response.status_code = stored.response_status
            body = stored.response_body
            response.headers["Location"] = body.get("location", "")
            return DocumentUploadResponse(**{
                k: v for k, v in body.items() if k != "location"
            })

    document = document_service.upload_document(
        file_content=file_content,
        original_filename=original_filename,
        session=session,
        db=db,
    )

    location = f"/api/v1/documents/{document.id}"
    response.headers["Location"] = location

    body = DocumentUploadResponse(
        id=document.id,
        state=document.state,
        fingerprint_sha256=document.fingerprint_sha256,
        safe_name=document.safe_name,
        uploaded_at=document.uploaded_at,
    )

    # Persist the idempotency record (best-effort; failure is non-fatal).
    if idempotency_key:
        req_hash = _request_hash(file_content, document_type)
        db.add(
            IdempotencyKey(
                key=idempotency_key,
                owner_id=session.organization_id,
                endpoint=ENDPOINT_UPLOAD,
                request_hash=req_hash,
                response_status=202,
                response_body={**body.model_dump(mode="json"), "location": location},
            )
        )
        db.commit()

    return body


@router.get("", response_model=dict)
def list_documents(
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> dict:
    """List documents for the caller's organization (newest first)."""
    docs = (
        db.execute(
            select(SourceDocument)
            .where(SourceDocument.owner_id == session.organization_id)
            .order_by(SourceDocument.uploaded_at.desc())
            .limit(100)
        )
        .scalars()
        .all()
    )
    return {
        "count": len(docs),
        "documents": [
            DocumentResponse(
                id=d.id,
                owner_id=d.owner_id,
                safe_name=d.safe_name,
                original_filename=d.original_filename,
                fingerprint_sha256=d.fingerprint_sha256,
                doc_type=d.doc_type,
                format_detected=d.format_detected,
                size_bytes=d.size_bytes,
                page_count=d.page_count,
                uploaded_by=d.uploaded_by,
                uploaded_at=d.uploaded_at,
                state=d.state,
                failure_reason=d.failure_reason,
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
            for d in docs
        ],
    }


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> DocumentResponse:
    """Retrieve a document by id (scoped to the caller's organization)."""
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
    return DocumentResponse(
        id=document.id,
        owner_id=document.owner_id,
        safe_name=document.safe_name,
        original_filename=document.original_filename,
        fingerprint_sha256=document.fingerprint_sha256,
        doc_type=document.doc_type,
        format_detected=document.format_detected,
        size_bytes=document.size_bytes,
        page_count=document.page_count,
        uploaded_by=document.uploaded_by,
        uploaded_at=document.uploaded_at,
        state=document.state,
        failure_reason=document.failure_reason,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.post(
    "/{document_id}/verify-fingerprint",
    response_model=FingerprintVerifyResponse,
    dependencies=[Depends(require_role("reader"))],
)
def verify_fingerprint(
    document_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> FingerprintVerifyResponse:
    """Verify document integrity by re-reading the stored file (NFR-3, V1-S2).

    Re-computes the SHA-256 of the stored file and compares it with the
    fingerprint recorded in the database. Returns ``matches: true/false``.
    """
    # Verify the document exists and belongs to the caller's org.
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

    matches = document_service.verify_fingerprint(
        document_id=document_id,
        owner_id=session.organization_id,
        db=db,
    )
    return FingerprintVerifyResponse(
        fingerprint=document.fingerprint_sha256,
        matches=matches,
    )


@router.get(
    "/{document_id}/content",
    dependencies=[Depends(require_role("reader"))],
)
def get_document_content(
    document_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> StreamingResponse:
    """Download the binary content of a source document (V1-S2).

    Returns the file with ``Content-Type: application/octet-stream`` and
    ``Content-Disposition: attachment; filename="<safe_name>"``.
    """
    # Verify the document exists and belongs to the caller's org.
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

    settings = get_settings()
    path = os.path.join(
        settings.DOCUMENT_STORAGE_PATH,
        str(session.organization_id),
        document.fingerprint_sha256,
    )
    if not os.path.isfile(path):
        raise NotFoundException("Document content")

    # Determine content type from format_detected.
    content_type_map = {
        "pdf_text": "application/pdf",
        "xml": "application/xml",
        "image": "application/octet-stream",
    }
    content_type = content_type_map.get(document.format_detected, "application/octet-stream")

    def _iter_file():
        with open(path, "rb") as fh:
            yield from iter(lambda: fh.read(65536), b"")

    return StreamingResponse(
        _iter_file(),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{document.safe_name}"',
            "ETag": f'"{document.fingerprint_sha256}"',
        },
    )


@router.delete(
    "/{document_id}",
    response_model=DocumentDeleteResponse,
    dependencies=[Depends(require_role("reader"))],
)
def delete_document(
    document_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> DocumentDeleteResponse:
    """Delete a document and all associated data (V1-S3).

    Cascades to: extractions, extracted_values, normalized_values,
    validated_values, expenses, expense_lines, extraction_jobs,
    document_splits, duplications, and audit events.

    Also removes the file from storage.

    Returns 200 on success, 404 if the document does not exist.
    """
    document_service.delete_document(
        document_id=document_id,
        owner_id=session.organization_id,
        actor_id=session.user_id,
        db=db,
    )
    return DocumentDeleteResponse(id=document_id)
