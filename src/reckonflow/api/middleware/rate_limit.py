"""Shared rate limit: Redis fixed window, in-memory fallback

Multi-instance demos need a shared counter. Redis INCR + EXPIRE does that.
When Redis is unreachable we fall back to the process-local deque so a cache
outage does not open the API to unlimited traffic — unlike idempotency, which
fails open to keep writes available.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from reckonflow.core.logging import get_logger

logger = get_logger(__name__)

# Skip probes and metrics — they are scraped frequently
_EXEMPT_PREFIXES = (
    "/health",
    "/api/v1/health",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi",
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        requests_per_minute: int = 120,
        enabled: bool = True,
        redis_factory: Callable[[], Redis] | None = None,
        key_prefix: str = "reckonflow:",
    ) -> None:
        super().__init__(app)
        self._limit = requests_per_minute
        self._enabled = enabled
        self._redis_factory = redis_factory
        self._key_prefix = key_prefix
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not self._enabled or any(
            request.url.path.startswith(prefix) for prefix in _EXEMPT_PREFIXES
        ):
            return await call_next(request)

        client_key = request.headers.get("X-API-Key") or (
            request.client.host if request.client else "anonymous"
        )

        if self._redis_factory is not None:
            allowed = await self._check_redis(client_key)
            if allowed is not None:
                if not allowed:
                    return self._too_many()
                return await call_next(request)

        if not self._check_memory(client_key):
            return self._too_many()
        return await call_next(request)

    def _too_many(self) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "error": "RateLimitExceeded",
                "detail": f"Limit is {self._limit} requests per minute",
            },
            headers={"Retry-After": "60"},
        )

    async def _check_redis(self, client_key: str) -> bool | None:
        """True/False when Redis works; None means fall back to memory"""
        bucket = f"{self._key_prefix}ratelimit:{client_key}"
        try:
            redis = self._redis_factory()  # type: ignore[misc]
            count = await redis.incr(bucket)
            if count == 1:
                await redis.expire(bucket, 60)
            return count <= self._limit
        except Exception as exc:
            logger.warning(
                "rate_limit.redis_unavailable",
                error=str(exc),
                path="fallback_memory",
            )
            return None

    def _check_memory(self, client_key: str) -> bool:
        now = time.monotonic()
        window = self._hits[client_key]
        cutoff = now - 60.0
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= self._limit:
            return False
        window.append(now)
        return True
