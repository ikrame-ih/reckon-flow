"""Safe retries for mutating requests via Idempotency-Key

Why: a client that posts an expense, times out, and retries must not create
two expenses. The network cannot distinguish a lost request from a lost
response, so the client supplies a key and the server guarantees the same key
yields the same effect and body.

Per mutating request with the header:
1. SET key <in-progress + fingerprint> NX EX ttl — atomic claim
2. On success, run the route and overwrite with captured status/headers/body
3. On failure: in-progress → 409; finished + same body → replay; different body → 409

The Redis key is scoped by method + path + Idempotency-Key only. Body hash is
stored as a fingerprint so reusing a key with a different payload is a conflict,
not a second execution.

Fail-open when Redis is unreachable — a cache outage should degrade the retry
guarantee, not take the API down.
See docs/adr/003-redis-idempotency.md
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

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
STATE_IN_PROGRESS = "in_progress"

# Transport headers — not part of response meaning; copying them corrupts replay
_SKIPPED_HEADERS = frozenset({"content-length", "transfer-encoding", "connection"})


def body_fingerprint(body: bytes) -> str:
    """Stable hash of the raw request body for mismatch detection"""
    return hashlib.sha256(body).hexdigest()


def build_cache_key(
    request: Request,
    idempotency_key: str,
    *,
    prefix: str = "reckonflow:",
) -> str:
    """Scope cache key by prefix, method, path, and client key (not body)"""
    return f"{prefix}idempotency:{request.method}:{request.url.path}:{idempotency_key}"


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Cache and replay responses for keyed mutating requests"""

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

        body = await request.body()
        fingerprint = body_fingerprint(body)
        cache_key = build_cache_key(request, idempotency_key, prefix=self._key_prefix)
        claim_payload = json.dumps(
            {"state": STATE_IN_PROGRESS, "fingerprint": fingerprint}
        )

        try:
            redis = self._redis_factory()
            claimed = await redis.set(cache_key, claim_payload, nx=True, ex=self._ttl)
        except Exception as exc:
            logger.warning(
                "idempotency.redis_unavailable", error=str(exc), path=request.url.path
            )
            return await call_next(request)

        if not claimed:
            conflict_or_replay = await self._handle_existing(
                redis, cache_key, fingerprint
            )
            if conflict_or_replay is not None:
                return conflict_or_replay
            try:
                claimed = await redis.set(
                    cache_key, claim_payload, nx=True, ex=self._ttl
                )
            except Exception as exc:
                logger.warning("idempotency.reclaim_failed", error=str(exc))
                return _conflict(
                    "Could not claim this Idempotency-Key after a failed "
                    "replay; retry shortly"
                )
            if not claimed:
                conflict_or_replay = await self._handle_existing(
                    redis, cache_key, fingerprint
                )
                if conflict_or_replay is not None:
                    return conflict_or_replay
                return _conflict(
                    "Could not claim or replay this Idempotency-Key; retry shortly"
                )

        response = await call_next(request)
        background = getattr(response, "background", None)
        captured = await _capture(response, fingerprint)
        await self._store(redis, cache_key, captured)
        rebuilt = _rebuild(captured)
        if background is not None:
            rebuilt.background = background
        return rebuilt

    async def _handle_existing(
        self, redis: Redis, cache_key: str, fingerprint: str
    ) -> Response | None:
        """Replay, 409, or None when the key can be reclaimed"""
        try:
            stored = await redis.get(cache_key)
        except Exception as exc:
            logger.warning("idempotency.read_failed", error=str(exc))
            return None

        if stored is None:
            return None

        # Legacy in-progress sentinel from older middleware versions
        if stored == "__in_progress__":
            return _conflict(
                "A request with this Idempotency-Key is still being "
                "processed; retry once it completes"
            )

        try:
            payload: dict[str, Any] = json.loads(stored)
        except json.JSONDecodeError:
            logger.warning("idempotency.corrupt_entry", key=cache_key)
            try:
                await redis.delete(cache_key)
            except Exception as exc:
                logger.warning("idempotency.corrupt_delete_failed", error=str(exc))
            return None

        stored_fp = str(payload.get("fingerprint", ""))
        if stored_fp and stored_fp != fingerprint:
            return _conflict(
                "Idempotency-Key was already used with a different request body"
            )

        if payload.get("state") == STATE_IN_PROGRESS:
            return _conflict(
                "A request with this Idempotency-Key is still being "
                "processed; retry once it completes"
            )

        if "status_code" not in payload:
            try:
                await redis.delete(cache_key)
            except Exception as exc:
                logger.warning("idempotency.corrupt_delete_failed", error=str(exc))
            return None

        response = _rebuild(payload)  # type: ignore[arg-type]
        response.headers[REPLAY_HEADER] = "true"
        return response

    async def _store(
        self, redis: Redis, cache_key: str, captured: CapturedResponse
    ) -> None:
        """Persist response, keeping the TTL the claim already set"""
        try:
            await redis.set(cache_key, json.dumps(captured), ex=self._ttl)
        except Exception as exc:
            logger.warning("idempotency.write_failed", error=str(exc))


class CapturedResponse(TypedDict):
    """Replayable response snapshot stored in Redis"""

    fingerprint: str
    status_code: int
    headers: dict[str, str]
    body: str


def _conflict(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"error": "IdempotencyConflict", "detail": detail},
    )


async def _capture(response: Response, fingerprint: str) -> CapturedResponse:
    """Drain a (possibly streaming) response into a replayable dict"""
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
        fingerprint=fingerprint,
        status_code=response.status_code,
        headers=headers,
        body=body.decode("utf-8", errors="replace"),
    )


def _rebuild(captured: CapturedResponse) -> Response:
    """Rebuild a live response from a captured snapshot"""
    return Response(
        content=captured["body"].encode("utf-8"),
        status_code=captured["status_code"],
        headers=dict(captured["headers"]),
    )
