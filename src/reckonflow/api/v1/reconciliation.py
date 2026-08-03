"""I expose reconciliation: suggest candidates, then confirm one

I keep suggestion and confirmation as two calls on purpose. Reconciliation is
a decision with money attached, so the default is that a human sees the
evidence and commits it; `auto` exists for the cases the engine is sure about
"""

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
        "Runs the hybrid pipeline and returns ranked candidates.\n\n"
        "1. SQL prefilter on a date window and an amount tolerance\n"
        "2. RapidFuzz `token_set_ratio` on the descriptions\n"
        "3. Embedding cosine, only when both rows already have an embedding\n"
        "4. Reciprocal Rank Fusion with `k=60`\n\n"
        "`confidence` is the fused score normalized against the best score "
        "reachable, so it stays comparable whether or not embeddings were "
        "available. Every individual signal is returned in `signals` so a "
        "reviewer can see why a line was proposed."
    ),
    responses={404: {"model": ErrorResponse, "description": "Unknown expense"}},
)
async def suggest_matches(
    expense_id: int,
    service: ReconciliationServiceDep,
    limit: int = Query(5, ge=1, le=25),
    date_window_days: int | None = Query(None, ge=0, le=90),
) -> MatchSuggestionResponse:
    """I return ranked bank candidates for one expense"""
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
        "Links the expense to the chosen bank line. Both rows are read with "
        "`SELECT ... FOR UPDATE` before the write, so two reviewers "
        "confirming the same suggestion cannot both succeed — the second gets "
        "409."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Unknown expense or bank line"},
        409: {"model": ErrorResponse, "description": "Already matched"},
    },
)
async def confirm_match(
    expense_id: int, payload: MatchConfirm, service: ReconciliationServiceDep
) -> MatchResult:
    """I commit one reviewer-confirmed match"""
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
        "Matches only when the top candidate clears the confidence threshold, "
        "the minimum text agreement, and is clearly ahead of the runner-up. "
        "Otherwise the expense moves to `pending_review` and no link is made."
    ),
    responses={404: {"model": ErrorResponse, "description": "Unknown expense"}},
)
async def auto_match(expense_id: int, service: ReconciliationServiceDep) -> MatchResult:
    """I match automatically or park the expense for a human"""
    expense, bank_transaction_id = await service.auto_reconcile(expense_id)
    return MatchResult(
        expense_id=expense.id,
        bank_transaction_id=bank_transaction_id or 0,
        match_status=expense.match_status,
    )
