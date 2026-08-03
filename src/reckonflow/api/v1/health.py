"""Health check routes for liveness probes"""

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
    """Minimal JSON confirming the process is alive"""
    settings = get_settings()
    return HealthResponse(status="ok", app=settings.app_name, version=__version__)
