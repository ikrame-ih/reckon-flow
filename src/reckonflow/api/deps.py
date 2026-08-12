"""Wire services and auth into routes via FastAPI dependencies

Routers validate input, call one service method, and shape the response.
Centralising construction here makes `dependency_overrides` easy in tests.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from reckonflow.core.config import get_settings
from reckonflow.core.db import get_db
from reckonflow.services.bank import BankService
from reckonflow.services.ledger import LedgerService
from reckonflow.services.receipts import ReceiptService
from reckonflow.services.reconciliation import ReconciliationService
from reckonflow.services.travel import TravelService

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _reject_bad_api_key(x_api_key: str | None) -> None:
    expected = get_settings().api_key
    if not expected:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


async def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """Gate all finance routes when API_KEY is configured

    Empty API_KEY disables the gate (local/CI). Production must set API_KEY —
    create_app refuses to boot otherwise. Liveness/readiness and interactive
    docs stay outside this dependency.
    """
    _reject_bad_api_key(x_api_key)


async def require_api_key_always(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """Gate any method when API_KEY is set — used for /metrics"""
    _reject_bad_api_key(x_api_key)


def get_ledger_service(session: DbSession) -> LedgerService:
    return LedgerService(session)


def get_travel_service(session: DbSession) -> TravelService:
    return TravelService(session)


def get_bank_service(session: DbSession) -> BankService:
    return BankService(session)


def get_receipt_service(session: DbSession) -> ReceiptService:
    return ReceiptService(session)


def get_reconciliation_service(session: DbSession) -> ReconciliationService:
    return ReconciliationService(session)


LedgerServiceDep = Annotated[LedgerService, Depends(get_ledger_service)]
TravelServiceDep = Annotated[TravelService, Depends(get_travel_service)]
BankServiceDep = Annotated[BankService, Depends(get_bank_service)]
ReceiptServiceDep = Annotated[ReceiptService, Depends(get_receipt_service)]
ReconciliationServiceDep = Annotated[
    ReconciliationService, Depends(get_reconciliation_service)
]
