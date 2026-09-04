"""Shared low-level helpers."""
from __future__ import annotations

import uuid


def uuid7() -> uuid.UUID:
    """Return a UUIDv7 when available (Python >= 3.14 / backport), else UUIDv4.

    The contract (openapi.yaml) references UUIDv7 identifiers. Python 3.9
    has no ``uuid.uuid7``; we fall back to UUIDv4 deterministically so the
    application remains importable and functional.
    """
    factory = getattr(uuid, "uuid7", None)
    if callable(factory):
        return factory()
    return uuid.uuid4()
