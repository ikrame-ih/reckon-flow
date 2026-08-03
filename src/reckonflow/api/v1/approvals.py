"""Approval state machine over HTTP — clients send actions, not target statuses"""

from __future__ import annotations

from fastapi import APIRouter, Query

from reckonflow.api.deps import TravelServiceDep
from reckonflow.models.travel import ApprovalStatus
from reckonflow.schemas.common import ErrorResponse
from reckonflow.schemas.travel import ApprovalAction, ApprovalRead, ApprovalTransition

router = APIRouter(prefix="/approvals", tags=["approvals"])

# Map requested action to target approval state
_ACTION_TARGETS: dict[ApprovalAction, ApprovalStatus] = {
    ApprovalAction.APPROVE: ApprovalStatus.APPROVED,
    ApprovalAction.REJECT: ApprovalStatus.REJECTED,
    ApprovalAction.MARK_PAID: ApprovalStatus.PAID,
}


@router.get(
    "",
    response_model=list[ApprovalRead],
    summary="List approvals",
    description=(
        "Returns approvals newest first. Filter with `status=pending` to get "
        "the reviewer queue."
    ),
)
async def list_approvals(
    service: TravelServiceDep,
    status: ApprovalStatus | None = Query(None, examples=["pending"]),
    limit: int = Query(100, ge=1, le=500),
) -> list[ApprovalRead]:
    """List approvals, optionally filtered by status"""
    approvals = await service.list_approvals(status=status, limit=limit)
    return [ApprovalRead.model_validate(approval) for approval in approvals]


@router.get(
    "/{approval_id}",
    response_model=ApprovalRead,
    summary="Get one approval",
    responses={404: {"model": ErrorResponse, "description": "Unknown approval"}},
)
async def get_approval(approval_id: int, service: TravelServiceDep) -> ApprovalRead:
    """One approval record"""
    approval = await service.get_approval(approval_id)
    return ApprovalRead.model_validate(approval)


@router.post(
    "/{approval_id}/transition",
    response_model=ApprovalRead,
    summary="Approve, reject, or mark an approval paid",
    description=(
        "Moves the approval along a legal edge only:\n\n"
        "- `approve`: pending -> approved\n"
        "- `reject`: pending -> rejected\n"
        "- `mark_paid`: approved -> paid\n\n"
        "Anything else returns 409. `rejected` and `paid` are terminal, which "
        "is what stops a payment from being recorded twice."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Unknown approval"},
        409: {"model": ErrorResponse, "description": "Illegal state transition"},
    },
)
async def transition_approval(
    approval_id: int, payload: ApprovalTransition, service: TravelServiceDep
) -> ApprovalRead:
    """Apply one reviewer decision"""
    approval = await service.transition_approval(
        approval_id,
        target=_ACTION_TARGETS[payload.action],
        reviewer=payload.reviewer,
        notes=payload.notes,
    )
    return ApprovalRead.model_validate(approval)
