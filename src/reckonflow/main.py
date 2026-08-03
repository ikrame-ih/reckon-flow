"""FastAPI application factory and CLI entry point

create_app() lets tests spin up a fresh app without uvicorn and swap the Redis
factory before middleware runs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis

from reckonflow import __version__
from reckonflow.api.deps import require_api_key_always
from reckonflow.api.errors import register_exception_handlers
from reckonflow.api.middleware.idempotency import IdempotencyMiddleware
from reckonflow.api.middleware.rate_limit import RateLimitMiddleware
from reckonflow.api.middleware.request_id import RequestIdMiddleware
from reckonflow.api.v1 import api_router
from reckonflow.api.v1.health import router as health_router
from reckonflow.core.config import get_settings
from reckonflow.core.logging import setup_logging
from reckonflow.core.redis import close_redis, get_redis

DESCRIPTION = """\
Headless API for corporate travel approvals, an immutable double-entry
ledger, LLM receipt extraction, and hybrid bank reconciliation.

**Things worth knowing before you call anything**

- Money is always a **string** in JSON. JSON numbers are floats in most
  clients, and a float has no place in a ledger.
- Mutating endpoints and `GET /metrics` require `X-API-Key` when `API_KEY`
  is configured.
- Every mutating endpoint honours an `Idempotency-Key` header. The first call
  with a given key runs; a retry replays the stored response and is marked
  with `Idempotency-Replayed: true`.
- The ledger is append-only. There is no update or delete endpoint — a
  correction is a new reversing transaction.
- Receipt text is treated as untrusted data. The model may only fill a strict
  extraction schema; it can never approve, pay, or modify anything.
"""

TAGS_METADATA = [
    {"name": "health", "description": "Liveness and dependency probes."},
    {"name": "accounts", "description": "Chart of accounts and balances."},
    {
        "name": "ledger",
        "description": "Append-only double-entry transactions.",
    },
    {"name": "travel", "description": "Trip pre-requests."},
    {"name": "approvals", "description": "The pending → approved → paid machine."},
    {"name": "expenses", "description": "Recorded spend awaiting reconciliation."},
    {"name": "bank", "description": "Bank statement CSV import."},
    {"name": "receipts", "description": "Upload and LLM extraction (202 + polling)."},
    {
        "name": "reconciliation",
        "description": "Hybrid matching: SQL prefilter, RapidFuzz, embeddings, RRF.",
    },
]


def create_app(*, redis_factory: Callable[[], Redis] | None = None) -> FastAPI:
    """Assemble the ReckonFlow API; optional redis_factory for tests"""
    settings = get_settings()
    setup_logging(debug=settings.debug)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Release Redis pool on shutdown so reloads stay clean"""
        yield
        await close_redis()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Outer middleware runs first on the way in (request-id → rate limit → idempotency)
    app.add_middleware(
        IdempotencyMiddleware,
        redis_factory=redis_factory or get_redis,
        ttl_seconds=settings.idempotency_ttl_seconds,
        enabled=settings.idempotency_enabled,
        key_prefix=settings.redis_key_prefix,
    )
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=settings.rate_limit_per_minute,
        enabled=settings.rate_limit_enabled,
    )
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    if settings.metrics_enabled:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator().instrument(app).expose(
            app,
            endpoint="/metrics",
            include_in_schema=False,
            dependencies=[Depends(require_api_key_always)],
        )

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        """Send browsers to the interactive docs — there is no HTML home page"""
        return RedirectResponse(url="/docs")

    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()


def run() -> None:
    """Entry point for `uv run reckonflow`"""
    import uvicorn

    uvicorn.run(
        "reckonflow.main:app",
        host="0.0.0.0",
        port=8000,
        reload=get_settings().debug,
    )
