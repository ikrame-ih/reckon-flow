"""Wire services into routes via FastAPI dependencies

Routers validate input, call one service method, and shape the response.
Building services here keeps that boundary honest and makes dependency_overrides
trivial in tests.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from reckonflow.core.db import get_db
from reckonflow.services.bank import BankService
from reckonflow.services.ledger import LedgerService
from reckonflow.services.receipts import ReceiptService
from reckonflow.services.reconciliation import ReconciliationService
from reckonflow.services.travel import TravelService

DbSession = Annotated[AsyncSession, Depends(get_db)]


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
