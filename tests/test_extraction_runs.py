"""Extraction tracing and job-id stability — no invented token metrics."""

from __future__ import annotations

from pathlib import Path

from reckonflow.core.config import get_settings
from reckonflow.services.receipts import ReceiptService
from reckonflow.tasks.receipts import run_extraction
from reckonflow.worker_queue import enqueue_extract, receipt_job_id

STUB_RECEIPT = (
    b"Berlin Taxi GmbH\n2026-07-21\nAirport transfer 45.50\nTotal: 45.50 EUR\n"
)


async def test_run_extraction_records_latency_row(
    session, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("RECEIPT_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()
    service = ReceiptService(session)
    receipt = await service.store_upload(
        filename="taxi.txt",
        content_type="text/plain",
        content=STUB_RECEIPT,
    )
    await session.commit()

    await run_extraction(session, receipt.id, attempt=1, job_id="receipt-extract:1")

    runs = await service.list_extraction_runs()
    assert len(runs) == 1
    row = runs[0]
    assert row.outcome == "success"
    assert row.provider == "stub"
    assert row.duration_ms >= 0
    assert row.token_count is None
    assert row.attempt == 1
    assert row.job_id == "receipt-extract:1"

    refreshed = await service.get_receipt(receipt.id)
    assert refreshed.status == "extracted"


async def test_enqueue_defaults_to_inline(monkeypatch) -> None:
    monkeypatch.setenv("RECEIPT_QUEUE", "inline")
    get_settings.cache_clear()
    assert await enqueue_extract(99) == "inline"
    assert receipt_job_id(99) == "receipt-extract:99"


def test_upload_reports_inline_queue(client, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RECEIPT_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()
    from test_api_routes import _approve_trip, _seed_chart

    _seed_chart(client)
    trip_id, _approval_id = _approve_trip(client)
    expense = client.post(
        "/api/v1/expenses",
        json={
            "travel_request_id": trip_id,
            "vendor": "Taxi",
            "description": "Airport",
            "amount": "45.50",
            "currency": "EUR",
            "expense_date": "2026-07-21",
        },
    )
    assert expense.status_code == 201, expense.text
    uploaded = client.post(
        "/api/v1/receipts",
        data={"expense_id": str(expense.json()["id"])},
        files={"file": ("taxi.txt", STUB_RECEIPT, "text/plain")},
    )
    assert uploaded.status_code == 202, uploaded.text
    assert uploaded.json()["queue"] == "inline"
