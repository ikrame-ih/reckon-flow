"""I map the append-only double-entry ledger tables

I store amounts as Numeric(15, 4) and keep currency on every entry
so multi-currency is ready even before FX conversion exists
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from reckonflow.models.base import Base

if TYPE_CHECKING:
    from reckonflow.models.account import Account


class LedgerTransaction(Base):
    """I group balanced ledger entries that must sum to zero together"""

    __tablename__ = "ledger_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    entries: Mapped[list[LedgerEntry]] = relationship(
        back_populates="transaction",
        cascade="all, delete-orphan",
    )


class LedgerEntry(Base):
    """I am one debit or credit line; I never update amounts after insert"""

    __tablename__ = "ledger_entries"
    __table_args__ = (
        # I reject rows where both sides are zero or both sides are non-zero
        CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)",
            name="ck_ledger_entry_one_sided",
        ),
        CheckConstraint("debit >= 0 AND credit >= 0", name="ck_ledger_entry_nonneg"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("ledger_transactions.id", ondelete="CASCADE"),
        index=True,
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id"),
        index=True,
    )
    debit: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"))
    credit: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)

    transaction: Mapped[LedgerTransaction] = relationship(back_populates="entries")
    account: Mapped[Account] = relationship(back_populates="entries")
