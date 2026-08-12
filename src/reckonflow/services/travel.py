"""Travel requests, approval state machine, and expenses

The state machine lives here rather than in the router because multiple
callers reach it: the API, the demo seed script, and (later) a reminder job.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from reckonflow.core.embeddings import text_embedding
from reckonflow.core.exceptions import (
    ConflictError,
    InvalidStateTransitionError,
    NotFoundError,
    ReckonFlowError,
)
from reckonflow.core.money import parse_money
from reckonflow.models import Account, Approval, Expense, TravelRequest
from reckonflow.models.travel import ApprovalStatus
from reckonflow.services.ledger import LedgerService

# Legal moves as data — adding a state should not mean editing branching logic
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

# Chart codes used when mark_paid posts the reimbursement
_CASH_CODE = "CASH"
_TRAVEL_CODE = "TRAVEL"
_SPENDABLE = frozenset({ApprovalStatus.APPROVED, ApprovalStatus.PAID})


class TravelService:
    """Travel and approval rules — kept out of the HTTP layer"""

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
        """Create request and pending approval in one unit of work

        A request without an approval row is invisible to the reviewer queue.
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
        """List approvals, optionally filtered to one queue such as pending"""
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
        """Move approval to a new status only along a legal edge

        Uses FOR UPDATE where the dialect supports it so two reviewers
        cannot both succeed from the same starting state. Marking paid also
        posts a balanced ledger transaction (TRAVEL debit / CASH credit).
        """
        if self._supports_for_update():
            stmt = select(Approval).where(Approval.id == approval_id).with_for_update()
            result = await self._session.execute(stmt)
            approval = result.scalar_one_or_none()
        else:
            approval = await self._session.get(Approval, approval_id)

        if approval is None:
            raise NotFoundError(f"Approval {approval_id} not found")

        current = ApprovalStatus(approval.status)
        if target not in ALLOWED_TRANSITIONS[current]:
            allowed = ", ".join(sorted(ALLOWED_TRANSITIONS[current])) or "nothing"
            raise InvalidStateTransitionError(
                f"Cannot move approval {approval_id} from {current} to {target};"
                f" allowed next: {allowed}"
            )

        if target == ApprovalStatus.PAID:
            await self._post_payment_ledger(approval)

        approval.status = target
        if reviewer is not None:
            approval.reviewer = reviewer
        if notes is not None:
            approval.notes = notes
        await self._session.flush()
        await self._session.refresh(approval)
        return approval

    async def _post_payment_ledger(self, approval: Approval) -> None:
        """Record the reimbursement in the double-entry ledger

        Prefer the sum of expenses on the trip (what was actually spent).
        Fall back to the pre-approval estimate when no expenses exist yet.
        """
        trip = await self.get_travel_request(approval.travel_request_id)
        cash = await self._account_by_code(_CASH_CODE)
        travel_acct = await self._account_by_code(_TRAVEL_CODE)

        spent = (
            await self._session.execute(
                select(func.coalesce(func.sum(Expense.amount), 0)).where(
                    Expense.travel_request_id == trip.id,
                )
            )
        ).scalar_one()
        amount_dec = parse_money(spent or 0)
        if amount_dec == 0:
            amount_dec = trip.estimated_amount
        amount = str(amount_dec)

        ledger = LedgerService(self._session)
        await ledger.create_balanced_transaction(
            reference=f"PAY-{approval.id}",
            description=(f"Travel payment: {trip.employee_name} → {trip.destination}"),
            lines=[
                {
                    "account_id": travel_acct.id,
                    "debit": amount,
                    "credit": "0",
                    "currency": trip.currency,
                },
                {
                    "account_id": cash.id,
                    "debit": "0",
                    "credit": amount,
                    "currency": trip.currency,
                },
            ],
        )

    async def _account_by_code(self, code: str) -> Account:
        result = await self._session.execute(
            select(Account).where(Account.code == code)
        )
        account = result.scalar_one_or_none()
        if account is None:
            raise ReckonFlowError(
                f"Account {code!r} is required before marking a trip paid; "
                "run the seed script or create CASH and TRAVEL accounts"
            )
        return account

    def _supports_for_update(self) -> bool:
        try:
            return self._session.get_bind().dialect.name in {
                "postgresql",
                "mysql",
                "oracle",
            }
        except Exception:
            return False

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
        """Record a spend; linked trips must already be approved or paid"""
        if travel_request_id is not None:
            trip = await self.get_travel_request(travel_request_id)
            if trip.approval is None:
                raise InvalidStateTransitionError(
                    f"Travel request {travel_request_id} has no approval row"
                )
            status = ApprovalStatus(trip.approval.status)
            if status not in _SPENDABLE:
                raise InvalidStateTransitionError(
                    f"Cannot attach expense to travel request {travel_request_id} "
                    f"while approval is {status.value}; approve the trip first"
                )
            if currency.upper() != trip.currency.upper():
                raise ConflictError(
                    f"Expense currency {currency.upper()!r} must match trip "
                    f"currency {trip.currency!r} (single-currency trips only)"
                )

        text = f"{vendor} {description}".strip()
        expense = Expense(
            travel_request_id=travel_request_id,
            vendor=vendor,
            description=description,
            amount=amount,
            currency=currency.upper(),
            expense_date=expense_date,
            embedding=text_embedding(text),
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
