"""I expose receipt upload and extraction lookup

The upload returns **202 Accepted**, not 200. Extraction calls an LLM on a
free tier: it can take seconds and it can be throttled. Blocking the upload on
that would make the client's timeout depend on someone else's quota, so I
accept the file, hand back a poll URL, and extract in the background
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)

from reckonflow.api.deps import ReceiptServiceDep
from reckonflow.core.config import get_settings
from reckonflow.models.travel import ReceiptStatus
from reckonflow.schemas.common import ErrorResponse
from reckonflow.schemas.receipt import (
    ReceiptAccepted,
    ReceiptExtractionRead,
    ReceiptRead,
)
from reckonflow.tasks.receipts import extract_receipt_task

router = APIRouter(prefix="/receipts", tags=["receipts"])

MAX_RECEIPT_BYTES = 5 * 1024 * 1024


@router.post(
    "",
    response_model=ReceiptAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a receipt for extraction",
    description=(
        "Stores the file and schedules extraction in the background, then "
        "returns **202 Accepted** with a `poll_url`.\n\n"
        "Receipt content is treated as untrusted data. The model may only "
        "produce a strict `ReceiptExtraction` (vendor, date, currency, "
        "subtotal, VAT, total, line items) — it cannot approve, pay, or "
        "modify anything. See ADR 002.\n\n"
        "With no `GROQ_API_KEY` configured the deterministic stub extractor "
        "runs instead, so the endpoint works offline."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Unknown expense"},
        413: {"model": ErrorResponse, "description": "File too large"},
    },
)
async def upload_receipt(
    service: ReceiptServiceDep,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Receipt file (text or OCR output)"),
    expense_id: int | None = Form(None, description="Expense this receipt documents"),
) -> ReceiptAccepted:
    """I accept a receipt, persist it, and queue extraction"""
    content = await file.read()
    if len(content) > MAX_RECEIPT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"I accept at most {MAX_RECEIPT_BYTES} bytes per receipt",
        )

    receipt = await service.store_upload(
        filename=file.filename or "receipt",
        content_type=file.content_type or "application/octet-stream",
        content=content,
        expense_id=expense_id,
    )
    background_tasks.add_task(extract_receipt_task, receipt.id)

    prefix = get_settings().api_v1_prefix
    return ReceiptAccepted(
        receipt_id=receipt.id, poll_url=f"{prefix}/receipts/{receipt.id}"
    )


@router.get(
    "/{receipt_id}",
    response_model=ReceiptRead,
    summary="Get receipt status",
    description="Poll this until `status` becomes `extracted` or `failed`.",
    responses={404: {"model": ErrorResponse, "description": "Unknown receipt"}},
)
async def get_receipt(receipt_id: int, service: ReceiptServiceDep) -> ReceiptRead:
    """I report where a receipt is in the extraction pipeline"""
    receipt = await service.get_receipt(receipt_id)
    return ReceiptRead.model_validate(receipt)


@router.get(
    "/{receipt_id}/extraction",
    response_model=ReceiptExtractionRead,
    summary="Get the structured extraction",
    description=(
        "Returns the validated `ReceiptExtraction`, or `null` while the "
        "background task is still running."
    ),
    responses={404: {"model": ErrorResponse, "description": "Unknown receipt"}},
)
async def get_receipt_extraction(
    receipt_id: int, service: ReceiptServiceDep
) -> ReceiptExtractionRead:
    """I return the structured data extracted from one receipt"""
    receipt = await service.get_receipt(receipt_id)
    return ReceiptExtractionRead(
        receipt_id=receipt.id,
        status=ReceiptStatus(receipt.status),
        extraction=service.read_extraction(receipt),
        error_message=receipt.error_message,
    )
