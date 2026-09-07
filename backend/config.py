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

    # LLM extraction fallback (ADR-0010: provider-neutral abstraction).
    # All parameters configurable via environment; no hardcoded provider.
    LLM_ENDPOINT: str = ""  # OpenAI-compatible endpoint URL
    LLM_MODEL: str = ""  # Model identifier
    LLM_API_KEY: str = ""  # API key (empty for local/no-auth)
    LLM_TIMEOUT_SECONDS: int = 30  # Request timeout
    LLM_MAX_RETRIES: int = 2  # Retry attempts on transient errors
    LLM_MAX_INPUT_CHARS: int = 8000  # Max chars of document text sent to LLM
    LLM_ENABLED: bool = True  # Master switch for LLM fallback


def get_settings() -> Settings:
    """Return the settings instance (re-reads env vars each call).

    Note: not cached so that environment variable changes (e.g. in tests)
    are picked up immediately. In production the env vars are stable so the
    overhead is negligible.
    """
    return Settings()
