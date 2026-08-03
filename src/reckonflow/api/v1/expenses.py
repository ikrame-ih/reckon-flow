"""I expose the expense routes

An expense is the pivot of reconciliation: it is what a receipt documents and
what a bank line eventually pays for
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Query, status

from reckonflow.api.deps import TravelServiceDep
from reckonflow.schemas.common import ErrorResponse
from reckonflow.schemas.travel import ExpenseCreate, ExpenseRead

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.post(
    "",
    response_model=ExpenseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record an expense",
    description=(
        "Records a spend, optionally linked to a travel request. New expenses "
        "start as `unmatched`; reconciliation moves them to `matched` or "
        "`pending_review`."
    ),
    responses={404: {"model": ErrorResponse, "description": "Unknown travel request"}},
)
async def create_expense(
    payload: ExpenseCreate, service: TravelServiceDep
) -> ExpenseRead:
    """I record one expense"""
    expense = await service.create_expense(
        travel_request_id=payload.travel_request_id,
        vendor=payload.vendor,
        description=payload.description,
        amount=Decimal(payload.amount),
        currency=payload.currency,
        expense_date=payload.expense_date,
    )
    return ExpenseRead.model_validate(expense)


@router.get(
    "",
    response_model=list[ExpenseRead],
    summary="List expenses",
    description="Returns the newest expenses first, optionally filtered by trip.",
)
async def list_expenses(
    service: TravelServiceDep,
    travel_request_id: int | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[ExpenseRead]:
    """I page expenses newest first"""
    expenses = await service.list_expenses(
        travel_request_id=travel_request_id, limit=limit, offset=offset
    )
    return [ExpenseRead.model_validate(expense) for expense in expenses]


@router.get(
    "/{expense_id}",
    response_model=ExpenseRead,
    summary="Get one expense",
    responses={404: {"model": ErrorResponse, "description": "Unknown expense"}},
)
async def get_expense(expense_id: int, service: TravelServiceDep) -> ExpenseRead:
    """I return one expense"""
    expense = await service.get_expense(expense_id)
    return ExpenseRead.model_validate(expense)
