"""ORM models for GastosE.

Importing this package registers every model on ``Base.metadata`` so that
``Base.metadata.create_all`` / Alembic autogenerate see the full schema.
"""
from backend.models.audit_event import AuditEvent
from backend.models.duplication import Duplication
from backend.models.document import SourceDocument
from backend.models.extraction import Extraction, ExtractedValue
from backend.models.extraction_job import ExtractionJob
from backend.models.idempotency_key import IdempotencyKey
from backend.models.normalized_value import NormalizedValue
from backend.models.organization import Organization
from backend.models.session import Session
from backend.models.user import User

__all__ = [
    "AuditEvent",
    "Duplication",
    "Extraction",
    "ExtractionJob",
    "ExtractedValue",
    "IdempotencyKey",
    "NormalizedValue",
    "Organization",
    "Session",
    "SourceDocument",
    "User",
]
