"""Receipt upload and extraction lookup — 202 Accepted, then background LLM"""

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
from reckonflow.core.exceptions import ConflictError, NotFoundError
from reckonflow.models.travel import ReceiptStatus
from reckonflow.schemas.common import ErrorResponse
from reckonflow.schemas.receipt import (
    ExtractionRunRead,
    ReceiptAccepted,
    ReceiptExtractionRead,
    ReceiptRead,
)
from reckonflow.tasks.receipts import extract_receipt_task
from reckonflow.worker_queue import enqueue_extract

router = APIRouter(prefix="/receipts", tags=["receipts"])

MAX_RECEIPT_BYTES = 5 * 1024 * 1024
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "text/plain",
        "text/csv",
        "text/markdown",
        "application/json",
        "application/octet-stream",
        "",
    }
)


@router.post(
    "",
    response_model=ReceiptAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a receipt for extraction",
    description=(
        "Returns **202** with a `poll_url`. Extraction runs in the background "
        "(Groq or stub). Accepts **plain text / OCR text only** — not PDF or "
        "images. Receipt text is untrusted — see ADR 002."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Unknown expense"},
        409: {"model": ErrorResponse, "description": "Expense already has a receipt"},
        413: {"model": ErrorResponse, "description": "File too large"},
        415: {"model": ErrorResponse, "description": "Unsupported media type"},
    },
)
async def upload_receipt(
    service: ReceiptServiceDep,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(
        ..., description="Receipt as plain text or OCR output (not PDF/image)"
    ),
    expense_id: int | None = Form(None, description="Expense this receipt documents"),
) -> ReceiptAccepted:
    """Persist upload and queue background extraction"""
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "Receipts must be plain text or OCR text "
                f"(got {content_type or 'unknown'}); PDF/images are not supported"
            ),
        )

    # Bound memory: stop after limit+1 so oversized uploads never fully load
    content = await file.read(MAX_RECEIPT_BYTES + 1)
    if len(content) > MAX_RECEIPT_BYTES:
        await file.close()
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Upload limit is {MAX_RECEIPT_BYTES} bytes per receipt",
        )

    try:
        receipt = await service.store_upload(
            filename=file.filename or "receipt.txt",
            content_type=content_type or "text/plain",
            content=content,
            expense_id=expense_id,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    queued = await enqueue_extract(receipt.id)
    if queued == "inline":
        background_tasks.add_task(extract_receipt_task, receipt.id)

    prefix = get_settings().api_v1_prefix
    return ReceiptAccepted(
        receipt_id=receipt.id,
        poll_url=f"{prefix}/receipts/{receipt.id}",
        queue=queued,
    )


@router.get(
    "/runs",
    response_model=list[ExtractionRunRead],
    summary="List recent extraction attempts",
    description=(
        "Latency and outcome per attempt. `token_count` is null for the stub "
        "and until a provider exposes usage. Not a product dashboard."
    ),
)
async def list_extraction_runs(
    service: ReceiptServiceDep,
    limit: int = 50,
) -> list[ExtractionRunRead]:
    """Newest extraction_runs first"""
    cap = min(max(limit, 1), 200)
    rows = await service.list_extraction_runs(limit=cap)
    return [ExtractionRunRead.model_validate(row) for row in rows]


@router.get(
    "/{receipt_id}",
    response_model=ReceiptRead,
    summary="Get receipt status",
    description="Poll this until `status` becomes `extracted` or `failed`.",
    responses={404: {"model": ErrorResponse, "description": "Unknown receipt"}},
)
async def get_receipt(receipt_id: int, service: ReceiptServiceDep) -> ReceiptRead:
    """Receipt status in the extraction pipeline"""
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
    """Structured extraction for one receipt"""
    receipt = await service.get_receipt(receipt_id)
    return ReceiptExtractionRead(
        receipt_id=receipt.id,
        status=ReceiptStatus(receipt.status),
        extraction=service.read_extraction(receipt),
        error_message=receipt.error_message,
    )
