"""Simple per-client rate limit for mutating and expensive routes

In-memory sliding window keyed by X-API-Key or client host. Good enough to
stop accidental hammering on a public demo; replace with Redis token bucket
for multi-instance deploys.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

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
    ) -> None:
        super().__init__(app)
        self._limit = requests_per_minute
        self._enabled = enabled
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not self._enabled or any(
            request.url.path.startswith(prefix) for prefix in _EXEMPT_PREFIXES
        ):
            return await call_next(request)

        key = request.headers.get("X-API-Key") or (
            request.client.host if request.client else "anonymous"
        )
        now = time.monotonic()
        window = self._hits[key]
        cutoff = now - 60.0
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= self._limit:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "RateLimitExceeded",
                    "detail": f"Limit is {self._limit} requests per minute",
                },
                headers={"Retry-After": "60"},
            )
        window.append(now)
        return await call_next(request)
