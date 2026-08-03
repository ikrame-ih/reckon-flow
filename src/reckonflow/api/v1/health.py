"""Health check routes for liveness and dependency probes"""

from fastapi import APIRouter
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
    summary="Liveness and dependency check",
    description=(
        "Returns ok when the process is up. Includes database and Redis reachability "
        "so operators can tell a cold cache from a dead API."
    ),
)
async def health() -> HealthResponse:
    """JSON confirming process liveness plus optional dependency status"""
    settings = get_settings()
    # Avoid poking real pools during unit tests / cold local starts when asked
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
    status = "ok" if db_ok else "degraded"
    return HealthResponse(
        status=status,
        app=settings.app_name,
        version=__version__,
        database=db_ok,
        redis=redis_ok,
    )


async def _database_ping() -> bool:
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
