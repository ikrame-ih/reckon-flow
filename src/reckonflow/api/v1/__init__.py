"""I aggregate every API v1 router behind one prefix

Keeping the assembly here means main.py mounts a single object, and adding a
resource is one import plus one include_router
"""

from fastapi import APIRouter

from reckonflow.api.v1 import (
    accounts,
    approvals,
    bank,
    expenses,
    health,
    ledger,
    receipts,
    reconciliation,
    travel,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(accounts.router)
api_router.include_router(ledger.router)
api_router.include_router(travel.router)
api_router.include_router(approvals.router)
api_router.include_router(expenses.router)
api_router.include_router(bank.router)
api_router.include_router(receipts.router)
api_router.include_router(reconciliation.router)
