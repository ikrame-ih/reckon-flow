"""Balanced double-entry writes and balances computed by aggregation

Ledger entry amounts are never updated — corrections are new reversing entries.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from reckonflow.core.exceptions import (
    ConflictError,
    NotFoundError,
    UnbalancedLedgerError,
)
from reckonflow.core.money import parse_money
from reckonflow.models import Account, LedgerEntry, LedgerTransaction


class LedgerService:
    """Ledger business rules — keeps HTTP routers thin"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_account(
        self, *, code: str, name: str, currency: str = "EUR"
    ) -> Account:
        """Open an account, rejecting a code that is already taken"""
        account = Account(code=code, name=name, currency=currency.upper())
        self._session.add(account)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            # The unique index is the real guard; a pre-check SELECT would
            # still lose the race between two concurrent requests
            await self._session.rollback()
            raise ConflictError(f"Account code {code!r} already exists") from exc
        return account

    async def get_account(self, account_id: int) -> Account:
        account = await self._session.get(Account, account_id)
        if account is None:
            raise NotFoundError(f"Account {account_id} not found")
        return account

    async def list_accounts(
        self, *, limit: int = 100, offset: int = 0
    ) -> list[Account]:
        """Page accounts ordered by code for stable output"""
        stmt = select(Account).order_by(Account.code).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_balanced_transaction(
        self,
        *,
        reference: str,
        description: str,
        lines: Sequence[Mapping[str, Any]],
    ) -> LedgerTransaction:
        """Insert a transaction only when debits equal credits

        Each line: account_id, debit, credit, optional currency, optional memo.
        Balance is re-checked here even though the schema already did — seed
        scripts and background jobs call this without going through HTTP.
        """
        if len(lines) < 2:
            raise UnbalancedLedgerError("I need at least two ledger lines")

        parsed: list[tuple[int, Decimal, Decimal, str, str | None]] = []
        total_debit = Decimal("0")
        total_credit = Decimal("0")

        for raw in lines:
            account_id = int(raw["account_id"])
            debit = parse_money(raw.get("debit", "0"))
            credit = parse_money(raw.get("credit", "0"))
            currency = str(raw.get("currency", "EUR")).upper()
            memo = raw.get("memo")
            memo_str = str(memo) if memo is not None else None

            if (debit > 0 and credit > 0) or (debit == 0 and credit == 0):
                raise UnbalancedLedgerError(
                    "Each line must be either a debit or a credit, not both or neither"
                )

            await self.get_account(account_id)
            total_debit += debit
            total_credit += credit
            parsed.append((account_id, debit, credit, currency, memo_str))

        if total_debit != total_credit:
            raise UnbalancedLedgerError(
                f"Unbalanced transaction: debit={total_debit} credit={total_credit}"
            )

        tx = LedgerTransaction(reference=reference, description=description)
        self._session.add(tx)
        await self._session.flush()

        for account_id, debit, credit, currency, memo_str in parsed:
            self._session.add(
                LedgerEntry(
                    transaction_id=tx.id,
                    account_id=account_id,
                    debit=debit,
                    credit=credit,
                    currency=currency,
                    memo=memo_str,
                )
            )
        await self._session.flush()
        await self._session.refresh(tx, attribute_names=["entries"])
        return tx

    async def get_transaction(self, transaction_id: int) -> LedgerTransaction:
        """Eager-load entries so serialization does not trigger lazy IO mid-response"""
        stmt = (
            select(LedgerTransaction)
            .options(selectinload(LedgerTransaction.entries))
            .where(LedgerTransaction.id == transaction_id)
        )
        result = await self._session.execute(stmt)
        tx = result.scalar_one_or_none()
        if tx is None:
            raise NotFoundError(f"Ledger transaction {transaction_id} not found")
        return tx

    async def account_balance(self, account_id: int) -> Decimal:
        """Balance is SUM(debit) - SUM(credit) — never a stored column"""
        await self.get_account(account_id)
        stmt = select(
            func.coalesce(func.sum(LedgerEntry.debit), 0),
            func.coalesce(func.sum(LedgerEntry.credit), 0),
        ).where(LedgerEntry.account_id == account_id)
        result = await self._session.execute(stmt)
        debit_sum, credit_sum = result.one()
        return parse_money(debit_sum or 0) - parse_money(credit_sum or 0)
