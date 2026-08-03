"""GET /metrics follows the API_KEY gate when configured"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from reckonflow.core.config import get_settings
from reckonflow.main import create_app


@pytest.fixture
def metrics_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("API_KEY", "metrics-secret")
    monkeypatch.setenv("METRICS_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        yield client
    get_settings.cache_clear()


def test_metrics_without_key_is_rejected(metrics_client: TestClient) -> None:
    response = metrics_client.get("/metrics")
    assert response.status_code == 401


def test_metrics_with_wrong_key_is_rejected(metrics_client: TestClient) -> None:
    response = metrics_client.get(
        "/metrics",
        headers={"X-API-Key": "wrong"},
    )
    assert response.status_code == 401


def test_metrics_with_correct_key_is_open(metrics_client: TestClient) -> None:
    response = metrics_client.get(
        "/metrics",
        headers={"X-API-Key": "metrics-secret"},
    )
    assert response.status_code == 200
    assert "http_requests" in response.text or "python_" in response.text
