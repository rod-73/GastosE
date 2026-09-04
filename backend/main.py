"""GastosE FastAPI application entrypoint.

Wires together:
- CORS (allow-all for development; tighten in production).
- Authentication middleware (opaque bearer token, ADR-0009).
- Exception handlers (RFC 7807 problem+json).
- Routers (auth, documents).
- ``/healthz`` (public, no auth).
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.exceptions import GastosEException
from backend.middleware.auth import auth_middleware
from backend.routers import auth as auth_router
from backend.routers import documents as documents_router
from backend.routers import expenses as expenses_router
from backend.routers import extractions as extractions_router
from backend.routers import worker as worker_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Build the FastAPI application (factory for testability)."""
    app = FastAPI(
        title="GastosE API",
        version="1.0.0",
        description="Gestión de gastos, facturas recibidas, tickets y documentos.",
    )

    # CORS (development: allow all origins).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Authentication middleware (opaque bearer token).
    app.middleware("http")(auth_middleware)

    # Exception handlers.
    @app.exception_handler(GastosEException)
    async def gastos_e_exception_handler(
        request: Request, exc: GastosEException
    ) -> JSONResponse:
        """Convert domain exceptions to RFC 7807 problem+json."""
        return JSONResponse(
            status_code=exc.status_code,
            media_type="application/problem+json",
            content={
                "type": f"https://gastos.example/errors/{exc.code}",
                "title": exc.message,
                "status": exc.status_code,
                "detail": exc.message,
                **({"errors": exc.details} if exc.details else {}),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Catch-all: never leak stack traces or internals (api-design)."""
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            media_type="application/problem+json",
            content={
                "type": "https://gastos.example/errors/internal",
                "title": "Internal server error",
                "status": 500,
            },
        )

    # Routers.
    app.include_router(auth_router.router)
    app.include_router(documents_router.router)
    app.include_router(worker_router.router)
    app.include_router(extractions_router.router)
    app.include_router(expenses_router.router)

    # Health endpoint (public, no auth).
    @app.get("/healthz", tags=["health"])
    def healthz() -> dict:
        """Liveness probe."""
        return {"status": "ok"}

    return app


app = create_app()
