"""X-API-Key gate on finance routes when API_KEY is set"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from reckonflow.api.deps import require_api_key
from reckonflow.core.config import get_settings
from reckonflow.main import create_app


@pytest.fixture
def authed_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("API_KEY", "test-secret")
    get_settings.cache_clear()

    app = FastAPI(dependencies=[Depends(require_api_key)])

    @app.get("/items")
    async def list_items() -> dict[str, str]:
        return {"ok": "true"}

    @app.post("/items")
    async def create_item() -> dict[str, str]:
        return {"created": "true"}

    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()


def test_mutating_without_key_is_rejected(authed_client: TestClient) -> None:
    response = authed_client.post("/items")
    assert response.status_code == 401


def test_mutating_with_wrong_key_is_rejected(authed_client: TestClient) -> None:
    response = authed_client.post("/items", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_get_without_key_is_rejected(authed_client: TestClient) -> None:
    response = authed_client.get("/items")
    assert response.status_code == 401


def test_get_with_correct_key_passes_auth(authed_client: TestClient) -> None:
    response = authed_client.get("/items", headers={"X-API-Key": "test-secret"})
    assert response.status_code == 200
    assert response.json() == {"ok": "true"}


def test_mutating_with_correct_key_passes_auth(authed_client: TestClient) -> None:
    response = authed_client.post("/items", headers={"X-API-Key": "test-secret"})
    assert response.status_code == 200
    assert response.json() == {"created": "true"}


def test_production_refuses_boot_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("API_KEY", "")
    monkeypatch.setenv("METRICS_ENABLED", "false")
    get_settings.cache_clear()
    app = create_app()
    with pytest.raises(RuntimeError, match="API_KEY is required"), TestClient(app):
        pass
    get_settings.cache_clear()


def test_health_stays_public_when_api_key_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("API_KEY", "test-secret")
    monkeypatch.setenv("METRICS_ENABLED", "false")
    get_settings.cache_clear()
    client = TestClient(create_app())
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200
    get_settings.cache_clear()
