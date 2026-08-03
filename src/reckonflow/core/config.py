"""I load application settings from environment variables

I keep secrets and environment-specific URLs out of source code
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """I centralize ReckonFlow configuration for every environment"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ReckonFlow"
    app_env: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    database_url: str = (
        "postgresql+asyncpg://reckonflow:reckonflow@localhost:5432/reckonflow"
    )
    redis_url: str = "redis://localhost:6379/0"

    # I use Groq's free tier for receipt extraction; empty key disables live calls
    # and makes the deterministic stub extractor take over, so demos and CI
    # never depend on a third-party quota
    groq_api_key: str = ""
    groq_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"

    # I keep uploaded receipts on the local filesystem for now; object storage
    # is a drop-in replacement later because only ReceiptService touches paths
    receipt_storage_dir: str = "var/receipts"

    idempotency_enabled: bool = True
    idempotency_ttl_seconds: int = 86_400
    # I namespace Redis keys so I can share one Upstash free DB with another app
    redis_key_prefix: str = "reckonflow:"

    # I only compare bank rows that fall inside this date window around the
    # expense date, which keeps the fuzzy stage cheap on large statements
    reconciliation_date_window_days: int = 5
    # I allow a small relative amount drift for card fees and FX rounding
    reconciliation_amount_tolerance: float = 0.02
    reconciliation_auto_match_threshold: float = 0.72
    # I refuse to auto-match on rank position alone; the text must also agree
    reconciliation_min_fuzzy_score: float = 60.0
    reconciliation_rrf_k: int = 60


@lru_cache
def get_settings() -> Settings:
    """I return one cached Settings instance per process"""
    return Settings()


def async_database_url(url: str | None = None) -> str:
    """I rewrite hosted Postgres URLs for SQLAlchemy async + asyncpg

    Neon and many dashboards hand out postgres:// or postgresql:// links
    asyncpg needs postgresql+asyncpg:// and ssl=require on Neon
    """
    raw = url if url is not None else get_settings().database_url
    if raw.startswith("postgres://"):
        raw = "postgresql+asyncpg://" + raw.removeprefix("postgres://")
    elif raw.startswith("postgresql://") and "+asyncpg" not in raw:
        raw = "postgresql+asyncpg://" + raw.removeprefix("postgresql://")
    if "ssl=" not in raw and ("neon.tech" in raw or "sslmode=" in raw):
        raw = raw.replace("sslmode=require", "ssl=require")
        if "ssl=" not in raw:
            joiner = "&" if "?" in raw else "?"
            raw = f"{raw}{joiner}ssl=require"
    return raw
