"""API v1 router aggregation.

Phase 0 only mounts the health route. Later phases add ledger, travel,
expenses, and reconciliation routers here.
"""

from fastapi import APIRouter

from reckonflow.api.v1 import health

api_router = APIRouter()
api_router.include_router(health.router)
