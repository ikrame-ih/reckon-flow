"""I map ledger accounts — named buckets that entries debit or credit"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from reckonflow.models.base import Base

if TYPE_CHECKING:
    from reckonflow.models.ledger import LedgerEntry


class Account(Base):
    """I represent one ledger account (cash, bank, travel expense, …)"""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    # ISO 4217 — ready before FX conversion exists
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    entries: Mapped[list[LedgerEntry]] = relationship(back_populates="account")

    def label(self) -> str:
        """I return a short human-readable label for logs and demos"""
        return f"{self.code} — {self.name} ({self.currency})"
