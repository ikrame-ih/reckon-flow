"""I expose bank statement import and lookup routes"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from reckonflow.api.deps import BankServiceDep
from reckonflow.schemas.bank import BankImportResult, BankTransactionRead
from reckonflow.schemas.common import ErrorResponse

router = APIRouter(prefix="/bank", tags=["bank"])

# I cap the upload so a hostile or accidental multi-gigabyte file cannot
# exhaust memory while I hold the decoded text
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@router.post(
    "/transactions/upload",
    response_model=BankImportResult,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a bank statement CSV",
    description=(
        "Accepts a CSV with `booking_date`, `amount`, `currency`, "
        "`description`, and optional `external_id` (common header spellings "
        "are mapped automatically). Every row is validated with Pydantic; bad "
        "rows are reported in `errors` while the good ones still import. Rows "
        "whose `external_id` already exists are counted as duplicates and "
        "skipped, so re-uploading yesterday's file is harmless."
    ),
    responses={413: {"model": ErrorResponse, "description": "File too large"}},
)
async def upload_bank_csv(
    service: BankServiceDep, file: UploadFile = File(...)
) -> BankImportResult:
    """I ingest one CSV statement and report exactly what happened"""
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"I accept at most {MAX_UPLOAD_BYTES} bytes per upload",
        )
    return await service.import_csv(content)


@router.get(
    "/transactions",
    response_model=list[BankTransactionRead],
    summary="List bank transactions",
    description="Returns bank lines newest first, optionally by match status.",
)
async def list_bank_transactions(
    service: BankServiceDep,
    match_status: str | None = Query(None, examples=["unmatched"]),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[BankTransactionRead]:
    """I page imported bank lines"""
    rows = await service.list_transactions(
        match_status=match_status, limit=limit, offset=offset
    )
    return [BankTransactionRead.model_validate(row) for row in rows]
