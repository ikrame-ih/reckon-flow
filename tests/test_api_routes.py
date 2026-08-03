"""HTTP smoke tests for business routes via the shared TestClient fixture"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_account_and_list(client: TestClient) -> None:
    created = client.post(
        "/api/v1/accounts",
        json={"code": "CASH", "name": "Cash", "currency": "EUR"},
    )
    assert created.status_code == 201, created.text
    listed = client.get("/api/v1/accounts")
    assert listed.status_code == 200
    assert any(row["code"] == "CASH" for row in listed.json())


def test_unbalanced_ledger_returns_422(client: TestClient) -> None:
    cash = client.post(
        "/api/v1/accounts", json={"code": "CASH", "name": "Cash", "currency": "EUR"}
    )
    travel = client.post(
        "/api/v1/accounts",
        json={"code": "TRAVEL", "name": "Travel", "currency": "EUR"},
    )
    assert cash.status_code == 201
    assert travel.status_code == 201
    cash_id = cash.json()["id"]
    travel_id = travel.json()["id"]

    response = client.post(
        "/api/v1/ledger/transactions",
        json={
            "reference": "BAD-1",
            "description": "unbalanced",
            "lines": [
                {
                    "account_id": travel_id,
                    "debit": "100.00",
                    "credit": "0",
                    "currency": "EUR",
                },
                {
                    "account_id": cash_id,
                    "debit": "0",
                    "credit": "50.00",
                    "currency": "EUR",
                },
            ],
        },
    )
    assert response.status_code == 422


def test_travel_approve_flow(client: TestClient) -> None:
    trip = client.post(
        "/api/v1/travel-requests",
        json={
            "employee_name": "Ada",
            "destination": "Berlin",
            "purpose": "Conf",
            "start_date": "2026-09-14",
            "end_date": "2026-09-17",
            "estimated_amount": "500.00",
            "currency": "EUR",
        },
    )
    assert trip.status_code == 201, trip.text
    approval_id = trip.json()["approval"]["id"]

    approved = client.post(
        f"/api/v1/approvals/{approval_id}/transition",
        json={"action": "approve", "reviewer": "finance"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
