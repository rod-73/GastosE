"""Organization model (tenant root, ADR-0008)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Text, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.utils import uuid7


class Organization(Base):
    """Tenant organization. All business data is scoped by ``owner_id``."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), primary_key=True, default=uuid7
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Organization id={self.id} name={self.name!r}>"
