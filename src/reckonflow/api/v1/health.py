"""Health check routes.

A health endpoint answers: "is the API process running?".
Containers and demos call this first before testing real features.
"""

from fastapi import APIRouter

from reckonflow import __version__
from reckonflow.core.config import get_settings
from reckonflow.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness check",
    description="Returns ok when the API process is running.",
)
async def health() -> HealthResponse:
    """Return a tiny JSON payload confirming the app is alive."""
    settings = get_settings()
    return HealthResponse(status="ok", app=settings.app_name, version=__version__)
