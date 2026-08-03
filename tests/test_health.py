"""Smoke-test health and the root redirect to docs"""

import pytest
from fastapi.testclient import TestClient

from reckonflow.core.config import get_settings
from reckonflow.main import create_app


def test_health_returns_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["app"] == "ReckonFlow"
    assert "version" in payload
    assert payload["database"] is True
    assert "X-Request-ID" in response.headers
    get_settings.cache_clear()


def test_versioned_health_returns_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    get_settings.cache_clear()


def test_health_degraded_when_redis_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Process stays up (200) but status flips when the cache is down."""
    monkeypatch.setenv("APP_ENV", "development")
    get_settings.cache_clear()

    async def _db_ok() -> bool:
        return True

    async def _redis_down() -> bool:
        return False

    monkeypatch.setattr(
        "reckonflow.api.v1.health._database_ping",
        _db_ok,
    )
    monkeypatch.setattr(
        "reckonflow.api.v1.health.redis_ping",
        _redis_down,
    )
    client = TestClient(create_app())
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["database"] is True
    assert payload["redis"] is False
    get_settings.cache_clear()


def test_root_redirects_to_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("METRICS_ENABLED", "false")
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/docs"
    get_settings.cache_clear()
