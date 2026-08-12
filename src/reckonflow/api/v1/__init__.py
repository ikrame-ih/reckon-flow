"""Aggregate API v1 routers — main.py mounts this single object.

Health/readiness stay outside this router so they remain public when
API_KEY is set.
"""

from fastapi import APIRouter, Depends

from reckonflow.api.deps import require_api_key
from reckonflow.api.v1 import (
    accounts,
    approvals,
    bank,
    expenses,
    ledger,
    receipts,
    reconciliation,
    travel,
)

api_router = APIRouter(dependencies=[Depends(require_api_key)])
api_router.include_router(accounts.router)
api_router.include_router(ledger.router)
api_router.include_router(travel.router)
api_router.include_router(approvals.router)
api_router.include_router(expenses.router)
api_router.include_router(bank.router)
api_router.include_router(receipts.router)
api_router.include_router(reconciliation.router)
