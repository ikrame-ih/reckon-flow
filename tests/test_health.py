"""Phase 0: health endpoint smoke test.

We use FastAPI's TestClient so we can call the API in-process
without starting a real HTTP server.
"""

from fastapi.testclient import TestClient

from reckonflow.main import create_app


def test_health_returns_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["app"] == "ReckonFlow"
    assert "version" in payload


def test_versioned_health_returns_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
