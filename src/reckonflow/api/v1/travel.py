"""Travel request routes"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Query, status

from reckonflow.api.deps import TravelServiceDep
from reckonflow.schemas.common import ErrorResponse
from reckonflow.schemas.travel import TravelRequestCreate, TravelRequestRead

router = APIRouter(prefix="/travel-requests", tags=["travel"])


@router.post(
    "",
    response_model=TravelRequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a travel request",
    description=(
        "Creates the trip request and immediately opens a **pending** approval "
        "for it, so nothing can exist outside the review queue. Send an "
        "`Idempotency-Key` header to make a retried submission safe."
    ),
)
async def create_travel_request(
    payload: TravelRequestCreate, service: TravelServiceDep
) -> TravelRequestRead:
    """Record a trip request with its pending approval"""
    request = await service.create_travel_request(
        employee_name=payload.employee_name,
        destination=payload.destination,
        purpose=payload.purpose,
        start_date=payload.start_date,
        end_date=payload.end_date,
        estimated_amount=Decimal(payload.estimated_amount),
        currency=payload.currency,
    )
    return TravelRequestRead.model_validate(request)


@router.get(
    "",
    response_model=list[TravelRequestRead],
    summary="List travel requests",
    description="Returns the newest requests first, each with its approval state.",
)
async def list_travel_requests(
    service: TravelServiceDep,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[TravelRequestRead]:
    """Page travel requests, newest first"""
    requests = await service.list_travel_requests(limit=limit, offset=offset)
    return [TravelRequestRead.model_validate(request) for request in requests]


@router.get(
    "/{travel_request_id}",
    response_model=TravelRequestRead,
    summary="Get one travel request",
    responses={404: {"model": ErrorResponse, "description": "Unknown request"}},
)
async def get_travel_request(
    travel_request_id: int, service: TravelServiceDep
) -> TravelRequestRead:
    """One travel request with its approval"""
    request = await service.get_travel_request(travel_request_id)
    return TravelRequestRead.model_validate(request)
