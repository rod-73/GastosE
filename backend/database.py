"""Database connection and session management (synchronous SQLAlchemy 2.0).

The API layer uses synchronous SQLAlchemy because no async driver
(asyncpg/psycopg) is available in the runtime. ``get_db`` is the FastAPI
dependency that yields one session per request.
"""
from __future__ import annotations

from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import get_settings


def _build_database_url() -> str:
    """Return a usable SQLAlchemy database URL.

    If the configured URL uses the plain ``postgresql://`` scheme (psycopg2
    driver), it is kept as-is. ``postgresql+asyncpg://`` URLs are not
    supported by the synchronous engine and are rejected at startup.
    """
    url = get_settings().DATABASE_URL
    if url.startswith("postgresql+asyncpg://"):
        raise RuntimeError(
            "DATABASE_URL uses the asyncpg driver but the API uses a "
            "synchronous engine. Use postgresql:// (psycopg2) instead."
        )
    return url


_engine = None
_SessionLocal = None


def get_engine():
    """Lazily create the database engine on first use."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            _build_database_url(),
            pool_pre_ping=True,
            future=True,
        )
    return _engine


def get_session_local():
    """Lazily create the session factory on first use."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            future=True,
        )
    return _SessionLocal


class Base(DeclarativeBase):
    """Declarative base for all GastosE ORM models."""


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one DB session per request."""
    db = get_session_local()()
    try:
        yield db
    finally:
        db.close()
