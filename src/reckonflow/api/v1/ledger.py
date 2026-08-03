"""Double-entry ledger routes — append-only; corrections are reversing entries"""

from __future__ import annotations

from fastapi import APIRouter, status

from reckonflow.api.deps import LedgerServiceDep
from reckonflow.schemas.common import ErrorResponse
from reckonflow.schemas.ledger import LedgerTransactionCreate, LedgerTransactionRead

router = APIRouter(prefix="/ledger", tags=["ledger"])


@router.post(
    "/transactions",
    response_model=LedgerTransactionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Post a balanced transaction",
    description=(
        "Writes a transaction and all of its entries in one database "
        "transaction. The request is rejected unless `SUM(debit) == "
        "SUM(credit)`, every line is single-sided, and each referenced account "
        "exists. Amounts are strings so no client turns them into floats."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Unknown account on a line"},
        422: {"model": ErrorResponse, "description": "Unbalanced or malformed lines"},
    },
)
async def create_transaction(
    payload: LedgerTransactionCreate, service: LedgerServiceDep
) -> LedgerTransactionRead:
    """Post one balanced transaction with its entries"""
    tx = await service.create_balanced_transaction(
        reference=payload.reference,
        description=payload.description,
        lines=[line.model_dump() for line in payload.lines],
    )
    return LedgerTransactionRead.model_validate(tx)


@router.get(
    "/transactions/{transaction_id}",
    response_model=LedgerTransactionRead,
    summary="Get a transaction with its entries",
    responses={404: {"model": ErrorResponse, "description": "Unknown transaction"}},
)
async def get_transaction(
    transaction_id: int, service: LedgerServiceDep
) -> LedgerTransactionRead:
    """One transaction with every attached entry"""
    tx = await service.get_transaction(transaction_id)
    return LedgerTransactionRead.model_validate(tx)
