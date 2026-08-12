"""Approval state machine — paid only after approved"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from reckonflow.core.exceptions import (
    ConflictError,
    InvalidStateTransitionError,
    NotFoundError,
)
from reckonflow.models.travel import ApprovalStatus
from reckonflow.services.travel import TravelService


async def _request(service: TravelService) -> int:
    request = await service.create_travel_request(
        employee_name="Ikrame Ibn Hayoun",
        destination="Berlin",
        purpose="Client onboarding workshop",
        start_date=date(2026, 9, 14),
        end_date=date(2026, 9, 17),
        estimated_amount=Decimal("980.00"),
    )
    return request.id


async def test_new_request_opens_a_pending_approval(session: AsyncSession) -> None:
    """Creating a travel request also creates a pending approval"""
    service = TravelService(session)
    request_id = await _request(service)

    request = await service.get_travel_request(request_id)
    assert request.approval is not None
    assert request.approval.status == ApprovalStatus.PENDING


async def test_full_happy_path_pending_to_approved_to_paid(
    session: AsyncSession,
) -> None:
    from reckonflow.services.ledger import LedgerService

    ledger = LedgerService(session)
    cash = await ledger.create_account(code="CASH", name="Cash")
    travel = await ledger.create_account(code="TRAVEL", name="Travel")

    service = TravelService(session)
    request = await service.get_travel_request(await _request(service))
    assert request.approval is not None
    approval_id = request.approval.id

    approved = await service.transition_approval(
        approval_id, target=ApprovalStatus.APPROVED, reviewer="finance.lead"
    )
    assert approved.status == ApprovalStatus.APPROVED
    assert approved.reviewer == "finance.lead"

    await service.create_expense(
        travel_request_id=request.id,
        vendor="Hotel Adlon",
        description="3 nights",
        amount=Decimal("612.40"),
        expense_date=date(2026, 9, 17),
    )

    paid = await service.transition_approval(approval_id, target=ApprovalStatus.PAID)
    assert paid.status == ApprovalStatus.PAID

    from sqlalchemy import func, select

    from reckonflow.models import LedgerTransaction

    count = await session.scalar(select(func.count()).select_from(LedgerTransaction))
    assert count == 1
    assert await ledger.account_balance(travel.id) == Decimal("612.40")
    assert await ledger.account_balance(cash.id) == Decimal("-612.40")


async def test_pending_cannot_jump_straight_to_paid(session: AsyncSession) -> None:
    """Pending cannot jump straight to paid"""
    service = TravelService(session)
    request = await service.get_travel_request(await _request(service))
    assert request.approval is not None

    with pytest.raises(InvalidStateTransitionError):
        await service.transition_approval(
            request.approval.id, target=ApprovalStatus.PAID
        )


async def test_rejected_is_terminal(session: AsyncSession) -> None:
    service = TravelService(session)
    request = await service.get_travel_request(await _request(service))
    assert request.approval is not None
    approval_id = request.approval.id

    await service.transition_approval(
        approval_id, target=ApprovalStatus.REJECTED, notes="Outside policy"
    )

    with pytest.raises(InvalidStateTransitionError):
        await service.transition_approval(approval_id, target=ApprovalStatus.APPROVED)


async def test_paid_cannot_be_paid_again(session: AsyncSession) -> None:
    """PAID is terminal — remaking payment would double-reimburse"""
    from reckonflow.services.ledger import LedgerService

    ledger = LedgerService(session)
    await ledger.create_account(code="CASH", name="Cash")
    await ledger.create_account(code="TRAVEL", name="Travel")

    service = TravelService(session)
    request = await service.get_travel_request(await _request(service))
    assert request.approval is not None
    approval_id = request.approval.id

    await service.transition_approval(approval_id, target=ApprovalStatus.APPROVED)
    await service.transition_approval(approval_id, target=ApprovalStatus.PAID)

    with pytest.raises(InvalidStateTransitionError):
        await service.transition_approval(approval_id, target=ApprovalStatus.PAID)


async def test_pending_queue_can_be_listed(session: AsyncSession) -> None:
    service = TravelService(session)
    await _request(service)
    second = await service.get_travel_request(await _request(service))
    assert second.approval is not None
    await service.transition_approval(
        second.approval.id, target=ApprovalStatus.APPROVED
    )

    pending = await service.list_approvals(status=ApprovalStatus.PENDING)
    assert len(pending) == 1


async def test_expense_can_hang_off_a_travel_request(session: AsyncSession) -> None:
    service = TravelService(session)
    request = await service.get_travel_request(await _request(service))
    assert request.approval is not None
    await service.transition_approval(
        request.approval.id, target=ApprovalStatus.APPROVED
    )

    expense = await service.create_expense(
        travel_request_id=request.id,
        vendor="Hotel Adlon",
        description="3 nights, Berlin",
        amount=Decimal("612.40"),
        expense_date=date(2026, 9, 17),
    )

    assert expense.travel_request_id == request.id
    assert expense.match_status == "unmatched"
    assert expense.embedding is not None
    assert len(await service.list_expenses(travel_request_id=request.id)) == 1


async def test_expense_on_pending_trip_is_rejected(session: AsyncSession) -> None:
    service = TravelService(session)
    request_id = await _request(service)

    with pytest.raises(InvalidStateTransitionError):
        await service.create_expense(
            travel_request_id=request_id,
            vendor="Hotel Adlon",
            description="3 nights, Berlin",
            amount=Decimal("612.40"),
            expense_date=date(2026, 9, 17),
        )


async def test_expense_currency_must_match_trip(session: AsyncSession) -> None:
    service = TravelService(session)
    request_id = await _request(service)
    request = await service.get_travel_request(request_id)
    assert request.approval is not None
    await service.transition_approval(
        request.approval.id, target=ApprovalStatus.APPROVED, reviewer="boss"
    )

    with pytest.raises(ConflictError, match="single-currency"):
        await service.create_expense(
            travel_request_id=request_id,
            vendor="Hotel Adlon",
            description="3 nights, Berlin",
            amount=Decimal("612.40"),
            currency="USD",
            expense_date=date(2026, 9, 17),
        )


async def test_expense_on_an_unknown_trip_is_rejected(session: AsyncSession) -> None:
    service = TravelService(session)

    with pytest.raises(NotFoundError):
        await service.create_expense(
            travel_request_id=4242,
            vendor="Hotel Adlon",
            description="3 nights, Berlin",
            amount=Decimal("612.40"),
            expense_date=date(2026, 9, 17),
        )


async def test_postgres_transition_emits_select_for_update() -> None:
    """Postgres path emits FOR UPDATE on approval rows"""
    from types import SimpleNamespace
    from typing import Any
    from unittest.mock import AsyncMock, MagicMock

    statements: list[str] = []

    async def execute(statement: Any, *args: Any, **kwargs: Any) -> Any:
        statements.append(str(statement))
        row = MagicMock()
        row.scalar_one_or_none.return_value = SimpleNamespace(
            id=1,
            status=ApprovalStatus.PENDING.value,
            reviewer=None,
            notes=None,
        )
        return row

    session = MagicMock()
    session.execute = AsyncMock(side_effect=execute)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.get_bind.return_value = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql")
    )

    service = TravelService(session)
    await service.transition_approval(1, target=ApprovalStatus.APPROVED)

    assert len(statements) == 1
    assert "FOR UPDATE" in statements[0]


async def test_sqlite_transition_skips_for_update(session: AsyncSession) -> None:
    service = TravelService(session)
    assert service._supports_for_update() is False
