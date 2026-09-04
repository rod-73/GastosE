"""Domain exceptions for GastosE.

Every exception carries a stable machine-readable ``code`` (used by the
API error handler to build RFC 7807 problem+json responses) and an HTTP
status code.
"""
from __future__ import annotations

from typing import Optional


class GastosEException(Exception):
    """Base class for all GastosE domain errors."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        details: Optional[dict] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class UnauthorizedException(GastosEException):
    """401: missing or invalid credentials/session."""

    def __init__(self) -> None:
        super().__init__("auth.unauthorized", "Authentication required", 401)


class ForbiddenException(GastosEException):
    """403: authenticated but insufficient role."""

    def __init__(self) -> None:
        super().__init__("auth.forbidden", "Insufficient permissions", 403)


class NotFoundException(GastosEException):
    """404: resource does not exist (or does not belong to the caller)."""

    def __init__(self, resource: str = "Resource") -> None:
        super().__init__("resource.not_found", f"{resource} not found", 404)


class DocumentTooLargeException(GastosEException):
    """413: upload exceeds MAX_UPLOAD_SIZE."""

    def __init__(self) -> None:
        super().__init__(
            "document.too_large",
            "The document exceeds the maximum size of 20 MB.",
            413,
        )


class UnsupportedFormatException(GastosEException):
    """415: file magic bytes do not match any supported format."""

    def __init__(self) -> None:
        super().__init__(
            "document.unsupported_format",
            "Unsupported document format",
            415,
        )


class DuplicateDocumentException(GastosEException):
    """409: a document with the same fingerprint already exists for the owner."""

    def __init__(self, existing_id: str) -> None:
        super().__init__(
            "conflict.duplicate",
            "Document already exists",
            409,
            {"existing_id": existing_id},
        )
