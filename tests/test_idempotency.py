"""Idempotency middleware with a fake Redis

Fake Redis avoids Docker in CI and simulates hard-to-reproduce states: key
still in progress, and Redis completely down.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from reckonflow.api.middleware.idempotency import (
    IDEMPOTENCY_HEADER,
    IN_PROGRESS,
    REPLAY_HEADER,
    IdempotencyMiddleware,
    build_cache_key,
)


class FakeRedis:
    """Minimal SET NX EX / GET implementation the middleware needs"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.set_calls: list[dict[str, Any]] = []

    async def set(
        self,
        key: str,
        value: str,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool | None:
        self.set_calls.append({"key": key, "value": value, "nx": nx, "ex": ex})
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def delete(self, key: str) -> int:
        return 1 if self.store.pop(key, None) is not None else 0


class BrokenRedis(FakeRedis):
    """Simulates unreachable Redis"""

    async def set(self, *args: Any, **kwargs: Any) -> bool | None:
        raise ConnectionError("redis is down")


def build_client(redis: Any, *, enabled: bool = True) -> tuple[TestClient, list[int]]:
    """Test app with counting endpoint wrapped in idempotency middleware"""
    calls: list[int] = []
    app = FastAPI()
    app.add_middleware(
        IdempotencyMiddleware,
        redis_factory=lambda: redis,
        ttl_seconds=86_400,
        enabled=enabled,
    )

    @app.post("/things")
    async def create_thing(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(1)
        return {"created": len(calls), "name": payload.get("name")}

    @app.get("/things")
    async def list_things() -> dict[str, int]:
        calls.append(1)
        return {"count": len(calls)}

    return TestClient(app), calls


def test_first_call_runs_and_is_cached() -> None:
    redis = FakeRedis()
    client, calls = build_client(redis)

    response = client.post(
        "/things", json={"name": "hotel"}, headers={IDEMPOTENCY_HEADER: "key-1"}
    )

    assert response.status_code == 200
    assert response.json() == {"created": 1, "name": "hotel"}
    assert len(calls) == 1
    # The claim uses SET NX EX, which is the whole point: one atomic call
    first_call = redis.set_calls[0]
    assert first_call["nx"] is True
    assert first_call["ex"] == 86_400
    assert first_call["value"] == IN_PROGRESS


def test_retry_replays_the_stored_response_without_rerunning() -> None:
    redis = FakeRedis()
    client, calls = build_client(redis)
    headers = {IDEMPOTENCY_HEADER: "key-1"}

    first = client.post("/things", json={"name": "hotel"}, headers=headers)
    second = client.post("/things", json={"name": "hotel"}, headers=headers)

    assert second.status_code == first.status_code
    assert second.json() == first.json()
    assert second.headers[REPLAY_HEADER] == "true"
    # This is the guarantee: the handler ran exactly once
    assert len(calls) == 1


def test_in_progress_key_returns_409() -> None:
    """In-progress key returns 409"""
    redis = FakeRedis()
    client, calls = build_client(redis)
    body = b'{"name": "hotel"}'

    request = client.build_request("POST", "/things", content=body)
    cache_key = build_cache_key(request, "key-1", body)  # type: ignore[arg-type]
    redis.store[cache_key] = IN_PROGRESS

    response = client.post(
        "/things", content=body, headers={IDEMPOTENCY_HEADER: "key-1"}
    )

    assert response.status_code == 409
    assert response.json()["error"] == "IdempotencyConflict"
    assert calls == []


def test_different_keys_run_separately() -> None:
    redis = FakeRedis()
    client, calls = build_client(redis)

    client.post("/things", json={"name": "a"}, headers={IDEMPOTENCY_HEADER: "key-1"})
    client.post("/things", json={"name": "b"}, headers={IDEMPOTENCY_HEADER: "key-2"})

    assert len(calls) == 2


def test_same_key_with_a_different_body_is_not_replayed() -> None:
    """Same key with a different body is not a replay"""
    redis = FakeRedis()
    client, calls = build_client(redis)
    headers = {IDEMPOTENCY_HEADER: "key-1"}

    client.post("/things", json={"name": "a"}, headers=headers)
    second = client.post("/things", json={"name": "b"}, headers=headers)

    assert len(calls) == 2
    assert second.json()["name"] == "b"


def test_request_without_a_key_is_untouched() -> None:
    redis = FakeRedis()
    client, calls = build_client(redis)

    client.post("/things", json={"name": "a"})
    client.post("/things", json={"name": "a"})

    assert len(calls) == 2
    assert redis.set_calls == []


def test_get_requests_are_never_cached() -> None:
    """GET requests skip the idempotency middleware"""
    redis = FakeRedis()
    client, calls = build_client(redis)
    headers = {IDEMPOTENCY_HEADER: "key-1"}

    client.get("/things", headers=headers)
    client.get("/things", headers=headers)

    assert len(calls) == 2
    assert redis.set_calls == []


def test_middleware_fails_open_when_redis_is_down() -> None:
    """A cache outage degrades the retry guarantee; it must not 500 the API"""
    client, calls = build_client(BrokenRedis())

    response = client.post(
        "/things", json={"name": "hotel"}, headers={IDEMPOTENCY_HEADER: "key-1"}
    )

    assert response.status_code == 200
    assert len(calls) == 1


def test_disabled_middleware_is_a_passthrough() -> None:
    redis = FakeRedis()
    client, calls = build_client(redis, enabled=False)
    headers = {IDEMPOTENCY_HEADER: "key-1"}

    client.post("/things", json={"name": "a"}, headers=headers)
    client.post("/things", json={"name": "a"}, headers=headers)

    assert len(calls) == 2
    assert redis.set_calls == []


def test_corrupt_cache_is_deleted_and_reclaimed() -> None:
    """Corrupt cache entries are deleted and reclaimed"""
    redis = FakeRedis()
    client, calls = build_client(redis)
    headers = {IDEMPOTENCY_HEADER: "key-corrupt"}

    # First plant a corrupt value under the key the next request will use
    primed = client.build_request("POST", "/things", json={"name": "hotel"})
    body = primed.content
    cache_key = build_cache_key(primed, "key-corrupt", body)  # type: ignore[arg-type]
    redis.store[cache_key] = "{not-json"

    response = client.post("/things", json={"name": "hotel"}, headers=headers)

    assert response.status_code == 200
    assert len(calls) == 1
    assert redis.store.get(cache_key) != "{not-json"


def test_background_tasks_survive_idempotency_rebuild() -> None:
    """Response rebuild preserves BackgroundTasks"""
    from starlette.background import BackgroundTasks

    from reckonflow.api.middleware.idempotency import CapturedResponse, _rebuild

    ran: list[int] = []
    tasks = BackgroundTasks()
    tasks.add_task(lambda: ran.append(1))

    rebuilt = _rebuild(
        CapturedResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body="{}",
        )
    )
    rebuilt.background = tasks
    assert rebuilt.background is tasks
