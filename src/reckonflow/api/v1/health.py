"""Liveness and readiness probes

Liveness always returns 200 while the process can answer. Readiness returns
503 when PostgreSQL is unreachable so orchestrators (Render) stop routing
traffic. Redis may be down without failing readiness — idempotency fails open
by design (ADR 003).
"""

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from reckonflow import __version__
from reckonflow.core.config import get_settings
from reckonflow.core.db import SessionLocal
from reckonflow.core.redis import redis_ping
from reckonflow.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description=(
        "Always HTTP 200 while the process is up. Dependency flags are "
        "informational; Redis or Postgres down does not change the status code."
    ),
)
async def health() -> HealthResponse:
    """Process is alive — suitable for a cheap uptime check"""
    settings = get_settings()
    if settings.app_env == "test":
        return HealthResponse(
            status="ok",
            app=settings.app_name,
            version=__version__,
            database=True,
            redis=True,
        )
    db_ok = await _database_ping()
    redis_ok = await redis_ping()
    status_label = "ok" if db_ok and redis_ok else "degraded"
    return HealthResponse(
        status=status_label,
        app=settings.app_name,
        version=__version__,
        database=db_ok,
        redis=redis_ok,
    )


@router.get(
    "/ready",
    response_model=HealthResponse,
    summary="Readiness probe",
    description=(
        "HTTP 200 when PostgreSQL is reachable; HTTP 503 otherwise. Redis is "
        "reported but does not fail readiness (idempotency fails open)."
    ),
    responses={503: {"description": "PostgreSQL unavailable"}},
)
async def ready(response: Response) -> HealthResponse:
    """Ready to serve finance traffic"""
    settings = get_settings()
    if settings.app_env == "test":
        return HealthResponse(
            status="ok",
            app=settings.app_name,
            version=__version__,
            database=True,
            redis=True,
        )
    db_ok = await _database_ping()
    redis_ok = await redis_ping()
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="unavailable",
            app=settings.app_name,
            version=__version__,
            database=False,
            redis=redis_ok,
        )
    status_label = "ok" if redis_ok else "degraded"
    return HealthResponse(
        status=status_label,
        app=settings.app_name,
        version=__version__,
        database=True,
        redis=redis_ok,
    )


async def _database_ping() -> bool:
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
