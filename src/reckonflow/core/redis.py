"""I own the shared async Redis client

I keep one lazily created client per process because redis-py already pools
connections internally: creating a client per request would throw that away
"""

from __future__ import annotations

from redis.asyncio import Redis

from reckonflow.core.config import get_settings

_client: Redis | None = None


def get_redis() -> Redis:
    """I return the process-wide Redis client, creating it on first use

    I decode responses so callers work with str, not bytes — the only thing I
    store is JSON
    """
    global _client
    if _client is None:
        settings = get_settings()
        _client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _client


async def close_redis() -> None:
    """I release the connection pool during application shutdown"""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def redis_ping() -> bool:
    """I report whether Redis answers, without raising into a health check"""
    try:
        return bool(await get_redis().ping())
    except Exception:
        return False
