"""I build the FastAPI application

I keep create_app() as a factory so my tests can spin up a fresh app
without starting uvicorn, and so a test can swap the Redis factory before the
middleware is ever hit
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from reckonflow import __version__
from reckonflow.api.errors import register_exception_handlers
from reckonflow.api.middleware.idempotency import IdempotencyMiddleware
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
- Every mutating endpoint honours an `Idempotency-Key` header. The first call
  with a given key runs; a retry replays the stored response and is marked
  with `Idempotency-Replayed: true`.
- The ledger is append-only. There is no update or delete endpoint — a
  correction is a new reversing transaction.
- Receipt text is treated as untrusted data. The model may only fill a strict
  extraction schema; it can never approve, pay, or modify anything.
"""

TAGS_METADATA = [
    {"name": "health", "description": "Liveness probes."},
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
    """I assemble the ReckonFlow API

    I accept a redis_factory so tests can inject a fake client instead of
    reaching a real server
    """
    settings = get_settings()
    setup_logging(debug=settings.debug)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """I release the Redis pool on shutdown so reloads stay clean"""
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

    app.add_middleware(
        IdempotencyMiddleware,
        redis_factory=redis_factory or get_redis,
        ttl_seconds=settings.idempotency_ttl_seconds,
        enabled=settings.idempotency_enabled,
        key_prefix=settings.redis_key_prefix,
    )
    register_exception_handlers(app)

    # I expose a top-level probe at GET /health
    app.include_router(health_router)
    # I also mount the same health route under the versioned API prefix
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()


def run() -> None:
    """I start uvicorn when I run `uv run reckonflow`"""
    import uvicorn

    uvicorn.run(
        "reckonflow.main:app",
        host="0.0.0.0",
        port=8000,
        reload=get_settings().debug,
    )
