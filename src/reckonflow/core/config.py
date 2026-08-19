"""Application settings loaded from environment variables"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for every environment"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ReckonFlow"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    # When set, all /api/v1 finance routes need matching X-API-Key.
    # Empty = disabled. APP_ENV=production refuses to boot if empty.
    api_key: str = ""

    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 120
    metrics_enabled: bool = True

    database_url: str = (
        "postgresql+asyncpg://reckonflow:reckonflow@localhost:5432/reckonflow"
    )
    redis_url: str = "redis://localhost:6379/0"

    # Groq free tier for receipts; empty key → deterministic stub (CI/demos)
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"

    # Local filesystem for now; object storage is a drop-in via ReceiptService
    receipt_storage_dir: str = "var/receipts"

    idempotency_enabled: bool = True
    idempotency_ttl_seconds: int = 86_400
    # Namespace keys when sharing one Redis instance across apps
    redis_key_prefix: str = "reckonflow:"

    # Bank rows within this window around expense date keep fuzzy stage cheap
    reconciliation_date_window_days: int = 5
    # Relative amount tolerance for card fees and FX rounding
    reconciliation_amount_tolerance: float = 0.02
    reconciliation_auto_match_threshold: float = 0.72
    # Auto-match needs text agreement, not rank position alone
    reconciliation_min_fuzzy_score: float = 60.0
    reconciliation_rrf_k: int = 60

    # inline = FastAPI BackgroundTasks (tests / no Redis). arq = durable Redis jobs.
    receipt_queue: str = "inline"
    receipt_job_max_tries: int = 3
    receipt_job_timeout_seconds: int = 120


@lru_cache
def get_settings() -> Settings:
    """Cached Settings singleton per process"""
    return Settings()


def async_database_url(url: str | None = None) -> str:
    """Rewrite hosted Postgres URLs for SQLAlchemy async + asyncpg

    Neon links use sslmode= and channel_binding=; asyncpg rejects
    channel_binding and wants ssl=require instead of sslmode.
    """
    from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

    raw = url if url is not None else get_settings().database_url
    if raw.startswith("postgres://"):
        raw = "postgresql+asyncpg://" + raw.removeprefix("postgres://")
    elif raw.startswith("postgresql://") and "+asyncpg" not in raw:
        raw = "postgresql+asyncpg://" + raw.removeprefix("postgresql://")

    parsed = urlparse(raw)
    # Drop query params asyncpg does not understand (Neon adds channel_binding)
    dropped = {"channel_binding", "sslmode"}
    query = {
        key: value
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in dropped
    }
    host = parsed.hostname or ""
    if "ssl" not in {k.lower() for k in query} and (
        "neon.tech" in host or "sslmode=" in (url or raw)
    ):
        query["ssl"] = "require"

    return urlunparse(parsed._replace(query=urlencode(query)))
