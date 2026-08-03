"""I load application settings from environment variables

I use pydantic-settings so each field has a type and a wrong value fails early
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """I centralize ReckonFlow config for Phase 0"""

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
    """I return a cached Settings instance (loaded once per process)"""
    return Settings()
