"""Reconciliation — suggest candidates, then confirm with human oversight"""

from __future__ import annotations

from fastapi import APIRouter, Query

from reckonflow.api.deps import ReconciliationServiceDep
from reckonflow.core.money import money_to_str
from reckonflow.schemas.common import ErrorResponse
from reckonflow.schemas.reconciliation import (
    MatchConfirm,
    MatchResult,
    MatchSignals,
    MatchSuggestion,
    MatchSuggestionResponse,
)

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])


@router.get(
    "/expenses/{expense_id}/suggestions",
    response_model=MatchSuggestionResponse,
    summary="Suggest bank lines for an expense",
    description=(
        "Ranked candidates via SQL prefilter, RapidFuzz, optional embeddings, "
        "and RRF (k=60). Per-signal scores are in `signals`."
    ),
    responses={404: {"model": ErrorResponse, "description": "Unknown expense"}},
)
async def suggest_matches(
    expense_id: int,
    service: ReconciliationServiceDep,
    limit: int = Query(5, ge=1, le=25),
    date_window_days: int | None = Query(None, ge=0, le=90),
) -> MatchSuggestionResponse:
    """Ranked bank candidates for one expense"""
    expense, ranked, considered = await service.suggest_matches(
        expense_id, limit=limit, date_window_days=date_window_days
    )
    return MatchSuggestionResponse(
        expense_id=expense.id,
        expense_amount=money_to_str(expense.amount),
        expense_date=expense.expense_date,
        candidates_considered=considered,
        suggestions=[
            MatchSuggestion(
                bank_transaction_id=item.bank_transaction.id,
                booking_date=item.bank_transaction.booking_date,
                amount=money_to_str(item.bank_transaction.amount),
                currency=item.bank_transaction.currency,
                description=item.bank_transaction.description,
                rrf_score=item.rrf_score,
                confidence=item.confidence,
                auto_matchable=item.auto_matchable,
                signals=MatchSignals(
                    fuzzy_score=item.fuzzy_score,
                    amount_score=item.amount_score,
                    date_score=item.date_score,
                    embedding_score=item.embedding_score,
                ),
            )
            for item in ranked
        ],
    )


@router.post(
    "/expenses/{expense_id}/match",
    response_model=MatchResult,
    summary="Confirm a match",
    description=(
        "Links expense ↔ bank line under `SELECT … FOR UPDATE`. A second "
        "confirm on the same rows returns **409**."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Unknown expense or bank line"},
        409: {"model": ErrorResponse, "description": "Already matched"},
    },
)
async def confirm_match(
    expense_id: int, payload: MatchConfirm, service: ReconciliationServiceDep
) -> MatchResult:
    """Commit a reviewer-confirmed match"""
    expense, bank_row = await service.confirm_match(
        expense_id, payload.bank_transaction_id
    )
    return MatchResult(
        expense_id=expense.id,
        bank_transaction_id=bank_row.id,
        match_status=expense.match_status,
    )


@router.post(
    "/expenses/{expense_id}/auto-match",
    response_model=MatchResult,
    summary="Auto-match when the engine is confident",
    description=(
        "Matches only when the top candidate clears confidence, fuzzy floor, "
        "and beats the runner-up; otherwise parks as `pending_review`."
    ),
    responses={404: {"model": ErrorResponse, "description": "Unknown expense"}},
)
async def auto_match(expense_id: int, service: ReconciliationServiceDep) -> MatchResult:
    """Auto-match when confident, otherwise park for review"""
    expense, bank_transaction_id = await service.auto_reconcile(expense_id)
    return MatchResult(
        expense_id=expense.id,
        bank_transaction_id=bank_transaction_id,
        match_status=expense.match_status,
    )
