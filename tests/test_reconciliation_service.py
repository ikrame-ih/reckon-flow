"""I test the reconciliation pipeline end to end against SQLite

The interesting cases are not the happy path: they are the prefilter throwing
away work, the engine refusing to guess between two equally good candidates,
and two reviewers racing to claim the same bank line
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from reckonflow.core.exceptions import ConflictError
from reckonflow.models import BankTransaction, Expense
from reckonflow.models.travel import MatchStatus
from reckonflow.services.reconciliation import ReconciliationService


async def _expense(session: AsyncSession, **overrides: Any) -> Expense:
    expense = Expense(
        vendor=overrides.pop("vendor", "Hotel Adlon"),
        description=overrides.pop("description", "3 nights Berlin"),
        amount=overrides.pop("amount", Decimal("612.40")),
        currency="EUR",
        expense_date=overrides.pop("expense_date", date(2026, 9, 17)),
        **overrides,
    )
    session.add(expense)
    await session.flush()
    return expense


async def _bank_row(session: AsyncSession, **overrides: Any) -> BankTransaction:
    row = BankTransaction(
        booking_date=overrides.pop("booking_date", date(2026, 9, 18)),
        amount=overrides.pop("amount", Decimal("612.40")),
        currency="EUR",
        description=overrides.pop("description", "HOTEL ADLON BERLIN CARD 4421"),
        match_status=overrides.pop("match_status", MatchStatus.UNMATCHED.value),
        **overrides,
    )
    session.add(row)
    await session.flush()
    return row


async def test_obvious_match_is_suggested_first(session: AsyncSession) -> None:
    expense = await _expense(session)
    target = await _bank_row(session)
    await _bank_row(
        session,
        booking_date=date(2026, 9, 16),
        amount=Decimal("610.00"),
        description="LUFTHANSA FLIGHT TICKET",
    )

    service = ReconciliationService(session)
    _, ranked, considered = await service.suggest_matches(expense.id)

    assert considered == 2
    assert ranked[0].bank_transaction.id == target.id
    assert ranked[0].confidence > ranked[1].confidence
    assert ranked[0].auto_matchable is True


async def test_prefilter_drops_rows_outside_the_window(
    session: AsyncSession,
) -> None:
    """The prefilter is what keeps this affordable on a real statement"""
    expense = await _expense(session)
    await _bank_row(session, booking_date=date(2026, 12, 1))  # far outside the window
    await _bank_row(session, amount=Decimal("2500.00"))  # far outside the tolerance

    service = ReconciliationService(session)
    _, ranked, considered = await service.suggest_matches(expense.id)

    assert considered == 0
    assert ranked == []


async def test_already_claimed_rows_are_never_suggested(
    session: AsyncSession,
) -> None:
    expense = await _expense(session)
    other = await _expense(session, vendor="Someone else")
    await _bank_row(
        session, match_status=MatchStatus.MATCHED.value, matched_expense_id=other.id
    )

    service = ReconciliationService(session)
    _, ranked, considered = await service.suggest_matches(expense.id)

    assert considered == 0
    assert ranked == []


async def test_negative_bank_amount_still_matches(session: AsyncSession) -> None:
    """Statements sign a payment negative; the expense form does not"""
    expense = await _expense(session)
    debit = await _bank_row(session, amount=Decimal("-612.40"))

    service = ReconciliationService(session)
    _, ranked, _ = await service.suggest_matches(expense.id)

    assert ranked[0].bank_transaction.id == debit.id
    assert ranked[0].amount_score == pytest.approx(1.0)


async def test_embeddings_add_a_ranking_when_present(session: AsyncSession) -> None:
    expense = await _expense(session, embedding=[1.0, 0.0, 0.0])
    await _bank_row(session, embedding=[1.0, 0.0, 0.0])

    service = ReconciliationService(session)
    _, ranked, _ = await service.suggest_matches(expense.id)

    assert ranked[0].embedding_score == pytest.approx(1.0)
    assert "embedding" in ranked[0].rankings_used


async def test_auto_reconcile_parks_an_ambiguous_case(session: AsyncSession) -> None:
    """Two identical candidates are not a decision, they are a coin flip"""
    expense = await _expense(session)
    await _bank_row(session, external_id="a")
    await _bank_row(session, external_id="b")

    service = ReconciliationService(session)
    result, bank_id = await service.auto_reconcile(expense.id)

    assert bank_id is None
    assert result.match_status == MatchStatus.PENDING_REVIEW


async def test_auto_reconcile_matches_a_clear_winner(session: AsyncSession) -> None:
    expense = await _expense(session)
    winner = await _bank_row(session)
    await _bank_row(
        session,
        booking_date=date(2026, 9, 21),
        amount=Decimal("620.00"),
        description="DB BAHN TICKET",
    )

    service = ReconciliationService(session)
    result, bank_id = await service.auto_reconcile(expense.id)

    assert bank_id == winner.id
    assert result.match_status == MatchStatus.MATCHED


async def test_second_reviewer_loses_the_race(session: AsyncSession) -> None:
    """Concurrency: the row lock plus a post-lock re-check is the guard

    On SQLite I cannot open two real transactions, so I assert the invariant
    the lock exists to protect: once a bank line is claimed, a second claim
    for a different expense is refused rather than silently overwriting
    """
    first = await _expense(session)
    second = await _expense(session, vendor="Another traveller")
    bank_row = await _bank_row(session)

    service = ReconciliationService(session)
    await service.confirm_match(first.id, bank_row.id)

    with pytest.raises(ConflictError):
        await service.confirm_match(second.id, bank_row.id)

    assert bank_row.matched_expense_id == first.id
    assert second.match_status == MatchStatus.UNMATCHED


async def test_confirming_twice_for_the_same_expense_conflicts(
    session: AsyncSession,
) -> None:
    expense = await _expense(session)
    bank_row = await _bank_row(session)

    service = ReconciliationService(session)
    await service.confirm_match(expense.id, bank_row.id)

    with pytest.raises(ConflictError):
        await service.confirm_match(expense.id, bank_row.id)


async def test_postgres_confirm_emits_select_for_update() -> None:
    """I prove the pessimistic lock is really requested on PostgreSQL

    SQLite cannot run FOR UPDATE, so I mock the session and inspect the SQL
    that reaches it — the assertion is about the statement, not the database
    """
    statements: list[str] = []

    async def execute(statement: Any, *args: Any, **kwargs: Any) -> Any:
        statements.append(str(statement))
        row = MagicMock()
        row.scalar_one_or_none.return_value = SimpleNamespace(
            id=1,
            match_status=MatchStatus.UNMATCHED.value,
            matched_expense_id=None,
        )
        return row

    session = MagicMock()
    session.execute = AsyncMock(side_effect=execute)
    session.flush = AsyncMock()
    session.get_bind.return_value = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql")
    )

    service = ReconciliationService(session)
    await service.confirm_match(1, 1)

    assert len(statements) == 2
    assert all("FOR UPDATE" in sql for sql in statements)


async def test_sqlite_confirm_skips_for_update(session: AsyncSession) -> None:
    """I must not emit a clause the test dialect would reject"""
    service = ReconciliationService(session)

    assert service._supports_row_locks() is False
