"""I aggregate API v1 routers

In Phase 0 I only mount health
Later I will add ledger, travel, expenses, and reconciliation routers here
"""

from fastapi import APIRouter

from reckonflow.api.v1 import health

api_router = APIRouter()
api_router.include_router(health.router)
