"""FastAPI application factory.

create_app() builds the app object. Keeping this in a function makes
testing easier: tests can create a fresh app without starting uvicorn.
"""

from fastapi import FastAPI

from reckonflow import __version__
from reckonflow.api.v1 import api_router
from reckonflow.api.v1.health import router as health_router
from reckonflow.core.config import get_settings
from reckonflow.core.logging import setup_logging


def create_app() -> FastAPI:
    """Build the ReckonFlow API application (Phase 0 skeleton)."""
    settings = get_settings()
    setup_logging(debug=settings.debug)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Headless API for corporate travel approvals, double-entry ledgering, "
            "AI receipt extraction, and hybrid bank reconciliation."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
    )
    # Top-level probe: GET /health
    app.include_router(health_router)
    # Versioned API: GET /api/v1/health (same handler for now)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()


def run() -> None:
    """CLI entrypoint used by `uv run reckonflow`."""
    import uvicorn

    uvicorn.run(
        "reckonflow.main:app",
        host="0.0.0.0",
        port=8000,
        reload=get_settings().debug,
    )
