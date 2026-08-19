"""FastAPI application factory and CLI entry point

create_app() lets tests spin up a fresh app without uvicorn and swap the Redis
factory before middleware runs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, RedirectResponse
from redis.asyncio import Redis
from scalar_fastapi import get_scalar_api_reference

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
from reckonflow.worker_queue import close_arq_pool

DESCRIPTION = """\
Headless API for corporate travel: approvals, double-entry ledger,
receipt extraction, and bank reconciliation.

- Money is a **JSON string** (`"120.50"`), never a float.
- Finance routes under `/api/v1` need `X-API-Key` when `API_KEY` is set
  (reads and writes). `/health`, `/ready`, and interactive docs stay public.
- Mutating routes honour `Idempotency-Key` (replay header:
  `Idempotency-Replayed: true`). Same key with a different body → 409.
- Ledger is append-only — fix mistakes with a reversing transaction.
- Receipt text is untrusted; the model only fills a strict schema (ADR 002).

Interactive docs: **Scalar** at `/docs`. Classic Swagger at `/swagger`,
ReDoc at `/redoc`.
"""

# Order matches the demo walkthrough
TAGS_METADATA = [
    {"name": "health", "description": "Liveness and readiness probes."},
    {"name": "travel", "description": "Trip pre-requests."},
    {"name": "approvals", "description": "pending → approved → paid."},
    {"name": "expenses", "description": "Spend awaiting reconciliation."},
    {"name": "bank", "description": "Statement CSV import."},
    {
        "name": "reconciliation",
        "description": "SQL prefilter + RapidFuzz + RRF matching.",
    },
    {"name": "accounts", "description": "Chart of accounts and balances."},
    {"name": "ledger", "description": "Append-only double-entry posts."},
    {"name": "receipts", "description": "Upload (202) + poll extraction."},
]

# Public paths that must not require ApiKeyAuth in OpenAPI
_PUBLIC_PATH_PREFIXES = ("/health", "/ready", "/docs", "/swagger", "/redoc", "/openapi")


def create_app(*, redis_factory: Callable[[], Redis] | None = None) -> FastAPI:
    """Assemble the ReckonFlow API; optional redis_factory for tests"""
    settings = get_settings()
    setup_logging(debug=settings.debug)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Refuse insecure production boots; release Redis on shutdown"""
        current = get_settings()
        if current.app_env == "production" and not current.api_key:
            raise RuntimeError(
                "API_KEY is required when APP_ENV=production "
                "(refuse to boot with an open finance API)"
            )
        yield
        await close_arq_pool()
        await close_redis()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        docs_url=None,
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
        redis_factory=redis_factory or get_redis,
        key_prefix=settings.redis_key_prefix,
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

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=TAGS_METADATA,
        )
        components = schema.setdefault("components", {})
        schemes = components.setdefault("securitySchemes", {})
        schemes["ApiKeyAuth"] = {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": (
                "Required on all /api/v1 finance routes when API_KEY is configured. "
                "Liveness, readiness, and docs stay public."
            ),
        }
        schemes["IdempotencyKey"] = {
            "type": "apiKey",
            "in": "header",
            "name": "Idempotency-Key",
            "description": (
                "Optional on mutating requests. Same key + same body replays; "
                "same key + different body returns 409."
            ),
        }
        # Apply API key security to finance operations; leave probes/docs open
        for path, methods in schema.get("paths", {}).items():
            if any(path.startswith(prefix) for prefix in _PUBLIC_PATH_PREFIXES):
                continue
            if not path.startswith("/api/v1"):
                continue
            for method, operation in methods.items():
                if method.startswith("x-") or not isinstance(operation, dict):
                    continue
                operation["security"] = [{"ApiKeyAuth": []}]
                if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
                    params = operation.setdefault("parameters", [])
                    if not any(
                        isinstance(p, dict)
                        and p.get("name") == "Idempotency-Key"
                        and p.get("in") == "header"
                        for p in params
                    ):
                        params.append(
                            {
                                "name": "Idempotency-Key",
                                "in": "header",
                                "required": False,
                                "schema": {"type": "string"},
                                "description": (
                                    "Safe retries: replay on match, "
                                    "409 on body mismatch."
                                ),
                            }
                        )
                    responses = operation.setdefault("responses", {})
                    responses.setdefault(
                        "401", {"description": "Invalid or missing X-API-Key"}
                    )
                    responses.setdefault(
                        "409",
                        {
                            "description": (
                                "Idempotency conflict (in progress or body mismatch)"
                            )
                        },
                    )
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]

    @app.get("/docs", include_in_schema=False)
    async def scalar_docs() -> HTMLResponse:
        """Modern API reference (Scalar) — default interactive docs"""
        return get_scalar_api_reference(
            openapi_url=app.openapi_url,
            title=f"{settings.app_name} API",
            hide_models=True,
            default_open_all_tags=False,
            expand_all_responses=False,
            telemetry=False,
            authentication={"preferredSecurityScheme": "ApiKeyAuth"},
        )

    @app.get("/swagger", include_in_schema=False)
    async def swagger_docs() -> HTMLResponse:
        """Classic Swagger UI if you prefer Try-it-out in the old layout"""
        return get_swagger_ui_html(
            openapi_url=app.openapi_url or "/openapi.json",
            title=f"{settings.app_name} — Swagger",
            swagger_ui_parameters={
                "docExpansion": "list",
                "defaultModelsExpandDepth": -1,
                "filter": True,
                "tryItOutEnabled": True,
                "displayRequestDuration": True,
            },
        )

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        """Send browsers to Scalar — there is no HTML home page"""
        return RedirectResponse(url="/docs")

    # Probes stay public (mounted twice: root + versioned alias)
    app.include_router(health_router)
    app.include_router(health_router, prefix=settings.api_v1_prefix)
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
