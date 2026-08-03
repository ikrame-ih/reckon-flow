"""I expose the ledger account routes

Accounts are the chart of accounts: every ledger entry points at one of them
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from reckonflow.api.deps import LedgerServiceDep
from reckonflow.core.money import money_to_str
from reckonflow.schemas.account import AccountBalanceRead, AccountCreate, AccountRead
from reckonflow.schemas.common import ErrorResponse

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post(
    "",
    response_model=AccountRead,
    status_code=status.HTTP_201_CREATED,
    summary="Open a ledger account",
    description=(
        "Creates one account in the chart of accounts. The `code` is unique, so "
        "replaying the same request returns 409 instead of a duplicate row. "
        "Send an `Idempotency-Key` header to get the original response replayed "
        "instead of an error."
    ),
    responses={409: {"model": ErrorResponse, "description": "Account code taken"}},
)
async def create_account(
    payload: AccountCreate, service: LedgerServiceDep
) -> AccountRead:
    """I open one account and return it with its generated id"""
    account = await service.create_account(
        code=payload.code, name=payload.name, currency=payload.currency
    )
    return AccountRead.model_validate(account)


@router.get(
    "",
    response_model=list[AccountRead],
    summary="List accounts",
    description="Returns accounts ordered by code, paged with limit and offset.",
)
async def list_accounts(
    service: LedgerServiceDep,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[AccountRead]:
    """I page the chart of accounts"""
    accounts = await service.list_accounts(limit=limit, offset=offset)
    return [AccountRead.model_validate(account) for account in accounts]


@router.get(
    "/{account_id}",
    response_model=AccountRead,
    summary="Get one account",
    responses={404: {"model": ErrorResponse, "description": "Unknown account"}},
)
async def get_account(account_id: int, service: LedgerServiceDep) -> AccountRead:
    """I return a single account or 404"""
    account = await service.get_account(account_id)
    return AccountRead.model_validate(account)


@router.get(
    "/{account_id}/balance",
    response_model=AccountBalanceRead,
    summary="Get an account balance",
    description=(
        "Computes `SUM(debit) - SUM(credit)` over every entry on the account. "
        "I never store a running balance: a cached total can drift from the "
        "entries, and the entries are the legal record."
    ),
    responses={404: {"model": ErrorResponse, "description": "Unknown account"}},
)
async def get_account_balance(
    account_id: int, service: LedgerServiceDep
) -> AccountBalanceRead:
    """I aggregate the entries of one account into a balance"""
    account = await service.get_account(account_id)
    balance = await service.account_balance(account_id)
    return AccountBalanceRead(
        account_id=account.id,
        code=account.code,
        currency=account.currency,
        balance=money_to_str(balance),
    )
