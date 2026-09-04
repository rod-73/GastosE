"""Audit service (V7-S1).

Implements:
- list_audit_events: list audit events with optional filters.
- get_audit_event: get a single audit event.

NFR-1: Append-only audit log (no UPDATE/DELETE operations).
INV-10: Provenance chain (before/after data preserved).
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from backend.models.audit_event import AuditEvent


def list_audit_events(
    owner_id: uuid.UUID,
    db: DbSession,
    entity_type: Optional[str] = None,
    entity_id: Optional[uuid.UUID] = None,
    action: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[AuditEvent]:
    """List audit events for the organization.

    Optionally filter by entity_type, entity_id, or action.
    Results are ordered by occurred_at descending (newest first).
    """
    query = select(AuditEvent).where(AuditEvent.owner_id == owner_id)

    if entity_type is not None:
        query = query.where(AuditEvent.entity_type == entity_type)

    if entity_id is not None:
        query = query.where(AuditEvent.entity_id == entity_id)

    if action is not None:
        query = query.where(AuditEvent.action == action)

    events = (
        db.execute(
            query.order_by(AuditEvent.occurred_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return list(events)


def get_audit_event(
    event_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: DbSession,
) -> AuditEvent:
    """Get a single audit event. Raises ValueError if not found."""
    event = (
        db.execute(
            select(AuditEvent).where(
                AuditEvent.id == event_id,
                AuditEvent.owner_id == owner_id,
            )
        )
        .scalars()
        .first()
    )
    if event is None:
        raise ValueError("Audit event not found")
    return event
