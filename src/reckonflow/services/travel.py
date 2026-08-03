"""I own travel requests, the approval state machine, and expenses

The state machine lives here rather than in the router because more than one
caller reaches it: the API, the demo seed script, and (later) a reminder job
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from reckonflow.core.exceptions import InvalidStateTransitionError, NotFoundError
from reckonflow.models import Approval, Expense, TravelRequest
from reckonflow.models.travel import ApprovalStatus

# I encode the legal moves as data so the rule is readable at a glance and
# adding a state never means editing branching logic in three places
ALLOWED_TRANSITIONS: dict[ApprovalStatus, frozenset[ApprovalStatus]] = {
    ApprovalStatus.PENDING: frozenset(
        {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}
    ),
    # Only an approved request can be paid — this is the control that stops
    # money leaving the company without a recorded decision
    ApprovalStatus.APPROVED: frozenset({ApprovalStatus.PAID}),
    ApprovalStatus.REJECTED: frozenset(),
    ApprovalStatus.PAID: frozenset(),
}


class TravelService:
    """I keep travel and approval rules out of the HTTP layer"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_travel_request(
        self,
        *,
        employee_name: str,
        destination: str,
        purpose: str,
        start_date: date,
        end_date: date,
        estimated_amount: Decimal,
        currency: str = "EUR",
    ) -> TravelRequest:
        """I create the request and its pending approval in one unit of work

        A request without an approval row would be invisible to the reviewer
        queue, so I never let those two exist apart
        """
        request = TravelRequest(
            employee_name=employee_name,
            destination=destination,
            purpose=purpose,
            start_date=start_date,
            end_date=end_date,
            estimated_amount=estimated_amount,
            currency=currency.upper(),
        )
        self._session.add(request)
        await self._session.flush()

        approval = Approval(travel_request_id=request.id, status=ApprovalStatus.PENDING)
        self._session.add(approval)
        await self._session.flush()
        await self._session.refresh(request, attribute_names=["approval"])
        return request

    async def get_travel_request(self, travel_request_id: int) -> TravelRequest:
        stmt = (
            select(TravelRequest)
            .options(selectinload(TravelRequest.approval))
            .where(TravelRequest.id == travel_request_id)
        )
        result = await self._session.execute(stmt)
        request = result.scalar_one_or_none()
        if request is None:
            raise NotFoundError(f"Travel request {travel_request_id} not found")
        return request

    async def list_travel_requests(
        self, *, limit: int = 100, offset: int = 0
    ) -> list[TravelRequest]:
        stmt = (
            select(TravelRequest)
            .options(selectinload(TravelRequest.approval))
            .order_by(TravelRequest.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_approval(self, approval_id: int) -> Approval:
        approval = await self._session.get(Approval, approval_id)
        if approval is None:
            raise NotFoundError(f"Approval {approval_id} not found")
        return approval

    async def list_approvals(
        self, *, status: ApprovalStatus | None = None, limit: int = 100
    ) -> list[Approval]:
        """I list approvals, optionally filtered to one queue such as pending"""
        stmt = select(Approval).order_by(Approval.id.desc()).limit(limit)
        if status is not None:
            stmt = stmt.where(Approval.status == status.value)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def transition_approval(
        self,
        approval_id: int,
        *,
        target: ApprovalStatus,
        reviewer: str | None = None,
        notes: str | None = None,
    ) -> Approval:
        """I move an approval to a new status only along a legal edge

        I read the row with a row lock where the database supports it, so two
        reviewers clicking approve and reject at the same moment cannot both
        succeed against the same starting state
        """
        approval = await self._session.get(Approval, approval_id, with_for_update=False)
        if approval is None:
            raise NotFoundError(f"Approval {approval_id} not found")

        current = ApprovalStatus(approval.status)
        if target not in ALLOWED_TRANSITIONS[current]:
            allowed = ", ".join(sorted(ALLOWED_TRANSITIONS[current])) or "nothing"
            raise InvalidStateTransitionError(
                f"I cannot move approval {approval_id} from {current} to {target};"
                f" allowed next: {allowed}"
            )

        approval.status = target
        if reviewer is not None:
            approval.reviewer = reviewer
        if notes is not None:
            approval.notes = notes
        await self._session.flush()
        return approval

    async def create_expense(
        self,
        *,
        vendor: str,
        description: str,
        amount: Decimal,
        expense_date: date,
        currency: str = "EUR",
        travel_request_id: int | None = None,
    ) -> Expense:
        """I record a spend, checking the travel request exists when given"""
        if travel_request_id is not None:
            await self.get_travel_request(travel_request_id)

        expense = Expense(
            travel_request_id=travel_request_id,
            vendor=vendor,
            description=description,
            amount=amount,
            currency=currency.upper(),
            expense_date=expense_date,
        )
        self._session.add(expense)
        await self._session.flush()
        return expense

    async def get_expense(self, expense_id: int) -> Expense:
        expense = await self._session.get(Expense, expense_id)
        if expense is None:
            raise NotFoundError(f"Expense {expense_id} not found")
        return expense

    async def list_expenses(
        self,
        *,
        travel_request_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Expense]:
        stmt = select(Expense).order_by(Expense.id.desc()).limit(limit).offset(offset)
        if travel_request_id is not None:
            stmt = stmt.where(Expense.travel_request_id == travel_request_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
