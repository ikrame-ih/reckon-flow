"""Application settings loaded from environment variables.

pydantic-settings reads values from the process environment and from a
local .env file. Each field has a type, so a wrong value fails early.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the ReckonFlow API (Phase 0)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ReckonFlow"
    app_env: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (loaded once per process)."""
    return Settings()
