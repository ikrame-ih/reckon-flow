"""Rate limit middleware — Redis fixed window with memory fallback"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from reckonflow.api.middleware.rate_limit import RateLimitMiddleware


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = seconds
        return True


class BrokenRedis(FakeRedis):
    async def incr(self, key: str) -> int:
        raise ConnectionError("redis is down")


def build_client(
    redis: Any | None,
    *,
    limit: int = 3,
) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=limit,
        enabled=True,
        redis_factory=(lambda: redis) if redis is not None else None,
        key_prefix="test:",
    )

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "true"}

    return TestClient(app)


def test_redis_allows_up_to_limit() -> None:
    redis = FakeRedis()
    client = build_client(redis, limit=3)

    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429
    assert redis.ttls  # expire set on first incr


def test_memory_fallback_when_redis_down() -> None:
    client = build_client(BrokenRedis(), limit=2)

    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429


def test_memory_only_when_no_redis_factory() -> None:
    client = build_client(None, limit=2)

    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429


def test_health_is_exempt() -> None:
    redis = FakeRedis()
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=1,
        enabled=True,
        redis_factory=lambda: redis,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/health").status_code == 200
    assert redis.store == {}
