"""Application configuration for GastosE.

Uses pydantic-settings so values can be overridden via environment
variables (e.g. ``GASTOSE_DATABASE_URL``) or a local ``.env`` file.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the GastosE API."""

    model_config = SettingsConfigDict(env_prefix="GASTOSE_", extra="ignore")

    DATABASE_URL: str = "postgresql://gastosE:gastosE@localhost:5432/gastosE"
    DOCUMENT_STORAGE_PATH: str = "/var/gastosE/documents"
    MAX_UPLOAD_SIZE: int = 20 * 1024 * 1024  # 20 MB
    SESSION_EXPIRY_DAYS: int = 30
    SECRET_KEY: str = "change-me-in-production"


def get_settings() -> Settings:
    """Return the settings instance (re-reads env vars each call).

    Note: not cached so that environment variable changes (e.g. in tests)
    are picked up immediately. In production the env vars are stable so the
    overhead is negligible.
    """
    return Settings()
