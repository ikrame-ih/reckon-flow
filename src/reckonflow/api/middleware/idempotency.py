"""I make retried mutating requests safe with an Idempotency-Key

Why this exists: a client that posts an expense, times out, and retries must
not create two expenses. The network cannot tell "the request was lost" apart
from "the response was lost", so the *client* supplies a key and I guarantee
that the same key produces the same effect and the same body

How it works, per mutating request that carries the header:

1. `SET key <in-progress> NX EX ttl` — one atomic call claims the key
2. If the claim succeeds, I run the route and overwrite the key with the
   captured status, headers, and body
3. If the claim fails, the key already exists:
   - still in progress  -> 409, because the first call has not finished
   - finished           -> I replay the stored response verbatim

I deliberately fail **open**: if Redis is unreachable I log and let the
request through. A cache outage should degrade the retry guarantee, not take
the whole API down
See docs/adr/003-redis-idempotency.md
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import TypedDict

from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from reckonflow.core.logging import get_logger

logger = get_logger(__name__)

IDEMPOTENCY_HEADER = "Idempotency-Key"
REPLAY_HEADER = "Idempotency-Replayed"
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
IN_PROGRESS = "__in_progress__"

# I never replay these: they describe the transport of the original response,
# not its meaning, and copying them corrupts the replayed body
_SKIPPED_HEADERS = frozenset({"content-length", "transfer-encoding", "connection"})


def build_cache_key(
    request: Request,
    idempotency_key: str,
    body: bytes,
    *,
    prefix: str = "reckonflow:",
) -> str:
    """I scope the key by app prefix, method, path, and a hash of the body

    The prefix lets me share one Upstash free-tier database with another
    project without key collisions. Scoping by route stops one key from
    accidentally replaying an unrelated endpoint's response
    """
    digest = hashlib.sha256(body).hexdigest()[:16]
    return (
        f"{prefix}idempotency:{request.method}:{request.url.path}:"
        f"{idempotency_key}:{digest}"
    )


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """I cache and replay responses for keyed mutating requests"""

    def __init__(
        self,
        app: ASGIApp,
        *,
        redis_factory: Callable[[], Redis],
        ttl_seconds: int = 86_400,
        enabled: bool = True,
        key_prefix: str = "reckonflow:",
    ) -> None:
        super().__init__(app)
        self._redis_factory = redis_factory
        self._ttl = ttl_seconds
        self._enabled = enabled
        self._key_prefix = key_prefix

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        idempotency_key = request.headers.get(IDEMPOTENCY_HEADER)
        if (
            not self._enabled
            or request.method not in MUTATING_METHODS
            or not idempotency_key
        ):
            return await call_next(request)

        # I must read the body here to hash it; Starlette caches it internally
        # so the downstream route can still read it afterwards
        body = await request.body()
        cache_key = build_cache_key(
            request, idempotency_key, body, prefix=self._key_prefix
        )

        try:
            redis = self._redis_factory()
            claimed = await redis.set(cache_key, IN_PROGRESS, nx=True, ex=self._ttl)
        except Exception as exc:
            logger.warning(
                "idempotency.redis_unavailable", error=str(exc), path=request.url.path
            )
            return await call_next(request)

        if not claimed:
            replayed = await self._replay(redis, cache_key)
            if replayed is not None:
                return replayed

        response = await call_next(request)
        captured = await _capture(response)
        await self._store(redis, cache_key, captured)
        return _rebuild(captured)

    async def _replay(self, redis: Redis, cache_key: str) -> Response | None:
        """I return the stored response, or a 409 while the first call runs"""
        try:
            stored = await redis.get(cache_key)
        except Exception as exc:
            logger.warning("idempotency.read_failed", error=str(exc))
            return None

        if stored is None:
            # The key expired between SET NX and GET; I let the request run
            return None
        if stored == IN_PROGRESS:
            return JSONResponse(
                status_code=409,
                content={
                    "error": "IdempotencyConflict",
                    "detail": (
                        "A request with this Idempotency-Key is still being "
                        "processed; retry once it completes"
                    ),
                },
            )
        try:
            captured: CapturedResponse = json.loads(stored)
        except json.JSONDecodeError:
            logger.warning("idempotency.corrupt_entry", key=cache_key)
            return None

        response = _rebuild(captured)
        response.headers[REPLAY_HEADER] = "true"
        return response

    async def _store(
        self, redis: Redis, cache_key: str, captured: CapturedResponse
    ) -> None:
        """I persist the response, keeping the TTL the claim already set"""
        try:
            await redis.set(cache_key, json.dumps(captured), ex=self._ttl)
        except Exception as exc:
            logger.warning("idempotency.write_failed", error=str(exc))


class CapturedResponse(TypedDict):
    """I am the replayable snapshot I keep in Redis"""

    status_code: int
    headers: dict[str, str]
    body: str


async def _capture(response: Response) -> CapturedResponse:
    """I drain a (possibly streaming) response into a replayable dict"""
    chunks: list[bytes] = []
    body_iterator = getattr(response, "body_iterator", None)
    if body_iterator is not None:
        async for chunk in body_iterator:
            chunks.append(chunk if isinstance(chunk, bytes) else str(chunk).encode())
        body = b"".join(chunks)
    else:
        body = getattr(response, "body", b"") or b""

    headers = {
        key: value
        for key, value in response.headers.items()
        if key.lower() not in _SKIPPED_HEADERS
    }
    return CapturedResponse(
        status_code=response.status_code,
        headers=headers,
        # I store text because Redis holds JSON; binary downloads are not
        # mutating endpoints, so this trade is safe here
        body=body.decode("utf-8", errors="replace"),
    )


def _rebuild(captured: CapturedResponse) -> Response:
    """I turn a captured snapshot back into a real response"""
    return Response(
        content=captured["body"].encode("utf-8"),
        status_code=captured["status_code"],
        headers=dict(captured["headers"]),
    )
