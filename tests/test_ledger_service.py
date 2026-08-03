"""Ledger invariant — unbalanced transactions must not persist

Checked at schema (HTTP) and service (seed/jobs) layers against different callers.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from reckonflow.core.exceptions import (
    ConflictError,
    NotFoundError,
    UnbalancedLedgerError,
)
from reckonflow.models import LedgerEntry
from reckonflow.schemas.ledger import LedgerTransactionCreate
from reckonflow.services.ledger import LedgerService


async def _two_accounts(service: LedgerService) -> tuple[int, int]:
    expense = await service.create_account(code="6400", name="Travel expenses")
    bank = await service.create_account(code="5100", name="Bank")
    return expense.id, bank.id


async def test_balanced_transaction_is_written(session: AsyncSession) -> None:
    service = LedgerService(session)
    expense_id, bank_id = await _two_accounts(service)

    tx = await service.create_balanced_transaction(
        reference="TRV-0001",
        description="Hotel Berlin",
        lines=[
            {"account_id": expense_id, "debit": "420.00"},
            {"account_id": bank_id, "credit": "420.00"},
        ],
    )

    assert tx.id is not None
    assert len(tx.entries) == 2
    assert await service.account_balance(expense_id) == Decimal("420")
    # The bank account paid, so its balance is the mirror image
    assert await service.account_balance(bank_id) == Decimal("-420")


async def test_unbalanced_transaction_raises_and_writes_nothing(
    session: AsyncSession,
) -> None:
    service = LedgerService(session)
    expense_id, bank_id = await _two_accounts(service)

    with pytest.raises(UnbalancedLedgerError):
        await service.create_balanced_transaction(
            reference="TRV-0002",
            description="Typo in the credit leg",
            lines=[
                {"account_id": expense_id, "debit": "420.00"},
                {"account_id": bank_id, "credit": "42.00"},
            ],
        )

    # Rejected transaction must leave no rows in the ledger tables
    count = await session.scalar(select(func.count()).select_from(LedgerEntry))
    assert count == 0


async def test_line_touching_both_sides_is_rejected(session: AsyncSession) -> None:
    service = LedgerService(session)
    expense_id, bank_id = await _two_accounts(service)

    with pytest.raises(UnbalancedLedgerError):
        await service.create_balanced_transaction(
            reference="TRV-0003",
            description="A line cannot be a debit and a credit",
            lines=[
                {"account_id": expense_id, "debit": "10.00", "credit": "10.00"},
                {"account_id": bank_id, "credit": "10.00"},
            ],
        )


async def test_single_line_transaction_is_rejected(session: AsyncSession) -> None:
    service = LedgerService(session)
    expense_id, _ = await _two_accounts(service)

    with pytest.raises(UnbalancedLedgerError):
        await service.create_balanced_transaction(
            reference="TRV-0004",
            description="Double entry needs two sides",
            lines=[{"account_id": expense_id, "debit": "10.00"}],
        )


async def test_unknown_account_raises_not_found(session: AsyncSession) -> None:
    service = LedgerService(session)
    expense_id, _ = await _two_accounts(service)

    with pytest.raises(NotFoundError):
        await service.create_balanced_transaction(
            reference="TRV-0005",
            description="Points at an account that does not exist",
            lines=[
                {"account_id": expense_id, "debit": "10.00"},
                {"account_id": 9999, "credit": "10.00"},
            ],
        )


async def test_duplicate_account_code_conflicts(session: AsyncSession) -> None:
    service = LedgerService(session)
    await service.create_account(code="6400", name="Travel expenses")

    with pytest.raises(ConflictError):
        await service.create_account(code="6400", name="Duplicate")


async def test_balance_is_aggregated_over_many_transactions(
    session: AsyncSession,
) -> None:
    """Balance is always aggregated — never stored"""
    service = LedgerService(session)
    expense_id, bank_id = await _two_accounts(service)

    for index, amount in enumerate(["10.25", "20.50", "5.25"]):
        await service.create_balanced_transaction(
            reference=f"TRV-10{index}",
            description=f"Spend {index}",
            lines=[
                {"account_id": expense_id, "debit": amount},
                {"account_id": bank_id, "credit": amount},
            ],
        )

    assert await service.account_balance(expense_id) == Decimal("36.00")


def test_schema_rejects_unbalanced_payload_before_the_database() -> None:
    """The service is the guard, but the client deserves a 422, not a 500"""
    with pytest.raises(ValidationError):
        LedgerTransactionCreate.model_validate(
            {
                "reference": "TRV-0006",
                "description": "Off by one cent",
                "lines": [
                    {"account_id": 1, "debit": "10.00"},
                    {"account_id": 2, "credit": "9.99"},
                ],
            }
        )


def test_schema_rejects_float_amounts() -> None:
    with pytest.raises(ValidationError):
        LedgerTransactionCreate.model_validate(
            {
                "reference": "TRV-0007",
                "description": "Floats are not money",
                "lines": [
                    {"account_id": 1, "debit": 10.0},
                    {"account_id": 2, "credit": 10.0},
                ],
            }
        )
