"""IdempotencyKey model (NFR-4: repeat of a mutation returns the same response)."""
from __future__ import annotations

from datetime import datetime

import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy import JSON, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class IdempotencyKey(Base):
    """Stores the first response of a mutation keyed by (key, owner, endpoint)."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<IdempotencyKey key={self.key!r} endpoint={self.endpoint!r}>"
