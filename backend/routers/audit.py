"""Audit endpoints (V7-S1).

- GET /api/v1/audit-events: list audit events for the organization.
- GET /api/v1/audit-events/{id}: get a single audit event.

NFR-1: Append-only audit log (no UPDATE/DELETE).
INV-10: Provenance chain (before/after data).
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from backend.database import get_db
from backend.exceptions import NotFoundException
from backend.middleware.auth import get_session, require_role
from backend.models.audit_event import AuditEvent
from backend.models.session import Session
from backend.services import audit_service

router = APIRouter(tags=["audit"])


# --- Schemas ---


class AuditEventResponse(BaseModel):
    """An audit event."""

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    action: str
    actor: uuid.UUID
    occurred_at: str
    before_data: Optional[dict]
    after_data: Optional[dict]
    created_at: str


class AuditEventListResponse(BaseModel):
    """List of audit events."""

    count: int
    events: List[AuditEventResponse]


# --- Endpoints ---


@router.get(
    "/api/v1/audit-events",
    response_model=AuditEventListResponse,
    dependencies=[Depends(require_role("reader"))],
)
def list_audit_events(
    entity_type: Optional[str] = None,
    entity_id: Optional[uuid.UUID] = None,
    action: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> AuditEventListResponse:
    """List audit events for the organization.

    Optionally filter by entity_type, entity_id, or action.
    """
    events = audit_service.list_audit_events(
        owner_id=session.organization_id,
        db=db,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        limit=limit,
        offset=offset,
    )
    return AuditEventListResponse(
        count=len(events),
        events=[
            AuditEventResponse(
                id=e.id,
                entity_type=e.entity_type,
                entity_id=e.entity_id,
                action=e.action,
                actor=e.actor,
                occurred_at=e.occurred_at.isoformat(),
                before_data=e.before_data,
                after_data=e.after_data,
                created_at=e.created_at.isoformat(),
            )
            for e in events
        ],
    )


@router.get(
    "/api/v1/audit-events/{event_id}",
    response_model=AuditEventResponse,
    dependencies=[Depends(require_role("reader"))],
)
def get_audit_event(
    event_id: uuid.UUID,
    session: Session = Depends(get_session),
    db: DbSession = Depends(get_db),
) -> AuditEventResponse:
    """Get a single audit event."""
    try:
        event = audit_service.get_audit_event(
            event_id=event_id,
            owner_id=session.organization_id,
            db=db,
        )
    except ValueError as e:
        raise NotFoundException(str(e))

    return AuditEventResponse(
        id=event.id,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        action=event.action,
        actor=event.actor,
        occurred_at=event.occurred_at.isoformat(),
        before_data=event.before_data,
        after_data=event.after_data,
        created_at=event.created_at.isoformat(),
    )
