"""Live PostgreSQL checks — skipped unless DATABASE_URL points at Postgres

CI applies Alembic migrations before pytest, then these tests exercise real
row locks (FOR UPDATE) that SQLite cannot provide.
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from reckonflow.core.exceptions import ConflictError
from reckonflow.models import BankTransaction, Expense
from reckonflow.models.travel import MatchStatus
from reckonflow.services.reconciliation import ReconciliationService

pytestmark = pytest.mark.postgres


@pytest.mark.asyncio
async def test_alembic_head_is_applied(pg_engine: AsyncEngine) -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config("alembic.ini")
    expected = ScriptDirectory.from_config(cfg).get_current_head()
    async with pg_engine.connect() as conn:
        version = (
            await conn.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one()
    assert version == expected


@pytest.mark.asyncio
async def test_confirm_emits_for_update_on_postgres(pg_session: AsyncSession) -> None:
    expense = Expense(
        vendor="Hotel",
        description="Berlin",
        amount=Decimal("120.00"),
        currency="EUR",
        expense_date=date(2026, 7, 26),
    )
    bank = BankTransaction(
        booking_date=date(2026, 7, 26),
        amount=Decimal("-120.00"),
        currency="EUR",
        description="HOTEL BERLIN",
        match_status=MatchStatus.UNMATCHED.value,
    )
    pg_session.add_all([expense, bank])
    await pg_session.flush()

    service = ReconciliationService(pg_session)
    assert service._supports_row_locks() is True

    matched, claimed = await service.confirm_match(expense.id, bank.id)
    assert matched.match_status == MatchStatus.MATCHED.value
    assert claimed.matched_expense_id == expense.id
    await pg_session.commit()


@pytest.mark.asyncio
async def test_for_update_blocks_concurrent_reader(pg_engine: AsyncEngine) -> None:
    """Second session cannot FOR UPDATE the same bank row while the first holds it"""
    maker = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as setup:
        expense = Expense(
            vendor="Hotel",
            description="Berlin",
            amount=Decimal("120.00"),
            currency="EUR",
            expense_date=date(2026, 7, 26),
        )
        bank = BankTransaction(
            booking_date=date(2026, 7, 26),
            amount=Decimal("-120.00"),
            currency="EUR",
            description="HOTEL BERLIN",
            match_status=MatchStatus.UNMATCHED.value,
        )
        setup.add_all([expense, bank])
        await setup.commit()
        expense_id = expense.id
        bank_id = bank.id

    async with maker() as holder:
        await holder.execute(text("SET LOCAL lock_timeout = '2s'"))
        bank_row = (
            await holder.execute(
                select(BankTransaction)
                .where(BankTransaction.id == bank_id)
                .with_for_update()
            )
        ).scalar_one()
        assert bank_row.id == bank_id

        async def _contended_confirm() -> None:
            async with maker() as contender:
                await contender.execute(text("SET LOCAL lock_timeout = '500ms'"))
                service = ReconciliationService(contender)
                await service.confirm_match(expense_id, bank_id)

        with pytest.raises(Exception) as exc_info:
            await asyncio.wait_for(_contended_confirm(), timeout=5)

        # asyncpg surfaces lock timeout as OperationalError / DBAPIError
        message = str(exc_info.value).lower()
        assert "lock" in message or "timeout" in message or "canceling" in message

        await holder.rollback()

    # After the holder releases, a confirm must succeed; a second confirm conflicts
    async with maker() as finisher:
        service = ReconciliationService(finisher)
        await service.confirm_match(expense_id, bank_id)
        await finisher.commit()

    async with maker() as again:
        service = ReconciliationService(again)
        with pytest.raises(ConflictError):
            await service.confirm_match(expense_id, bank_id)


@pytest.mark.asyncio
async def test_ledger_entries_reject_update_and_delete(
    pg_session: AsyncSession,
) -> None:
    from reckonflow.models import Account, LedgerEntry, LedgerTransaction

    cash = Account(code="CASH", name="Cash", currency="EUR")
    travel = Account(code="TRAVEL", name="Travel", currency="EUR")
    pg_session.add_all([cash, travel])
    await pg_session.flush()

    tx = LedgerTransaction(reference="IMM-1", description="seed")
    pg_session.add(tx)
    await pg_session.flush()
    debit = LedgerEntry(
        transaction_id=tx.id,
        account_id=travel.id,
        debit=Decimal("10.00"),
        credit=Decimal("0"),
        currency="EUR",
    )
    credit = LedgerEntry(
        transaction_id=tx.id,
        account_id=cash.id,
        debit=Decimal("0"),
        credit=Decimal("10.00"),
        currency="EUR",
    )
    pg_session.add_all([debit, credit])
    await pg_session.flush()
    await pg_session.commit()

    with pytest.raises(Exception, match="append-only"):
        await pg_session.execute(
            text("UPDATE ledger_entries SET memo = 'x' WHERE id = :id"),
            {"id": debit.id},
        )
        await pg_session.commit()

    await pg_session.rollback()

    with pytest.raises(Exception, match="append-only"):
        await pg_session.execute(
            text("DELETE FROM ledger_entries WHERE id = :id"),
            {"id": debit.id},
        )
        await pg_session.commit()


@pytest.mark.asyncio
async def test_concurrent_csv_import_dedupes_external_id(
    pg_engine: AsyncEngine,
) -> None:
    """Two sessions importing the same external_id must not 500"""
    from reckonflow.services.bank import BankService

    maker = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)
    csv_body = (
        b"booking_date,amount,currency,description,external_id\n"
        b"2026-09-16,-120.00,EUR,HOTEL RACE,EXT-RACE-1\n"
    )

    async def _import_once() -> int:
        async with maker() as session:
            service = BankService(session)
            result = await service.import_csv(csv_body)
            await session.commit()
            return result.inserted

    first, second = await asyncio.gather(_import_once(), _import_once())
    assert first + second == 1

    async with maker() as session:
        count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM bank_transactions "
                    "WHERE external_id = 'EXT-RACE-1'"
                )
            )
        ).scalar_one()
    assert count == 1
