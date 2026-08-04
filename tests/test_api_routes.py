"""HTTP smoke tests for business routes via the shared TestClient fixture"""

from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient


def _seed_chart(client: TestClient) -> tuple[int, int]:
    cash = client.post(
        "/api/v1/accounts",
        json={"code": "CASH", "name": "Cash", "currency": "EUR"},
    )
    travel = client.post(
        "/api/v1/accounts",
        json={"code": "TRAVEL", "name": "Travel", "currency": "EUR"},
    )
    assert cash.status_code == 201, cash.text
    assert travel.status_code == 201, travel.text
    return cash.json()["id"], travel.json()["id"]


def _approve_trip(client: TestClient) -> tuple[int, int]:
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
    trip_id = trip.json()["id"]
    approval_id = trip.json()["approval"]["id"]
    approved = client.post(
        f"/api/v1/approvals/{approval_id}/transition",
        json={"action": "approve", "reviewer": "finance"},
    )
    assert approved.status_code == 200
    return trip_id, approval_id


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
    cash_id, travel_id = _seed_chart(client)

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
    _seed_chart(client)
    _, approval_id = _approve_trip(client)
    listed = client.get("/api/v1/approvals")
    assert listed.status_code == 200
    assert any(row["id"] == approval_id for row in listed.json())


def test_mark_paid_posts_ledger(client: TestClient) -> None:
    cash_id, travel_id = _seed_chart(client)
    trip_id, approval_id = _approve_trip(client)

    expense = client.post(
        "/api/v1/expenses",
        json={
            "travel_request_id": trip_id,
            "vendor": "Hotel Mitte",
            "description": "3 nights",
            "amount": "120.00",
            "currency": "EUR",
            "expense_date": "2026-09-16",
        },
    )
    assert expense.status_code == 201, expense.text

    paid = client.post(
        f"/api/v1/approvals/{approval_id}/transition",
        json={"action": "mark_paid", "reviewer": "finance"},
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "paid"

    travel_bal = client.get(f"/api/v1/accounts/{travel_id}/balance")
    cash_bal = client.get(f"/api/v1/accounts/{cash_id}/balance")
    assert travel_bal.status_code == 200
    assert cash_bal.status_code == 200
    # Posts the sum of trip expenses (120), not the 500 estimate
    assert travel_bal.json()["balance"] in {"120.0000", "120.00"}
    assert cash_bal.json()["balance"] in {"-120.0000", "-120.00"}


def test_bank_import_and_recon_confirm(client: TestClient) -> None:
    _seed_chart(client)
    trip_id, _ = _approve_trip(client)

    expense = client.post(
        "/api/v1/expenses",
        json={
            "travel_request_id": trip_id,
            "vendor": "Hotel Mitte",
            "description": "Hotel Mitte Berlin",
            "amount": "120.00",
            "currency": "EUR",
            "expense_date": "2026-09-16",
        },
    )
    assert expense.status_code == 201, expense.text
    expense_id = expense.json()["id"]

    csv_body = (
        "booking_date,amount,currency,description,external_id\n"
        "2026-09-16,-120.00,EUR,LUXO HOTEL MITTE BERLIN,ext-1\n"
    )
    uploaded = client.post(
        "/api/v1/bank/transactions/upload",
        files={"file": ("stmt.csv", BytesIO(csv_body.encode()), "text/csv")},
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["inserted"] == 1

    suggestions = client.get(
        f"/api/v1/reconciliation/expenses/{expense_id}/suggestions"
    )
    assert suggestions.status_code == 200, suggestions.text
    payload = suggestions.json()
    assert payload["candidates_considered"] >= 1
    bank_id = payload["suggestions"][0]["bank_transaction_id"]

    matched = client.post(
        f"/api/v1/reconciliation/expenses/{expense_id}/match",
        json={"bank_transaction_id": bank_id},
    )
    assert matched.status_code == 200, matched.text
    assert matched.json()["match_status"] == "matched"

    again = client.post(
        f"/api/v1/reconciliation/expenses/{expense_id}/match",
        json={"bank_transaction_id": bank_id},
    )
    assert again.status_code == 409


def test_receipt_upload_returns_202_and_polls(client: TestClient) -> None:
    _seed_chart(client)
    trip_id, _ = _approve_trip(client)
    expense = client.post(
        "/api/v1/expenses",
        json={
            "travel_request_id": trip_id,
            "vendor": "Taxi",
            "description": "Airport run",
            "amount": "34.50",
            "currency": "EUR",
            "expense_date": "2026-09-15",
        },
    )
    assert expense.status_code == 201, expense.text
    expense_id = expense.json()["id"]

    receipt_text = b"Taxi Berlin\nDate: 2026-09-15\nTotal: 34.50 EUR\nThank you\n"
    uploaded = client.post(
        "/api/v1/receipts",
        data={"expense_id": str(expense_id)},
        files={"file": ("taxi.txt", BytesIO(receipt_text), "text/plain")},
    )
    assert uploaded.status_code == 202, uploaded.text
    receipt_id = uploaded.json()["receipt_id"]
    poll_url = uploaded.json()["poll_url"]
    assert poll_url.endswith(f"/receipts/{receipt_id}")

    polled = client.get(f"/api/v1/receipts/{receipt_id}")
    assert polled.status_code == 200
    assert polled.json()["status"] in {
        "uploaded",
        "pending",
        "extracted",
        "failed",
    }
