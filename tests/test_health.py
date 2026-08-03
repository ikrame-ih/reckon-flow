"""Smoke-test health and the root redirect to docs"""

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


def test_root_redirects_to_docs() -> None:
    client = TestClient(create_app())
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/docs"
