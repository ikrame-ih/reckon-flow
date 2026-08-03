"""Shared async Redis client — one lazy client per process.

redis-py pools connections internally; a client per request would waste that.
"""

from __future__ import annotations

from redis.asyncio import Redis

from reckonflow.core.config import get_settings

_client: Redis | None = None


def get_redis() -> Redis:
    """Process-wide Redis client, created on first use (decode_responses for JSON)"""
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
    """Release connection pool during application shutdown"""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def redis_ping() -> bool:
    """Whether Redis answers — never raises into a health check"""
    try:
        return bool(await get_redis().ping())
    except Exception:
        return False
