"""Double-entry ledger request/response shapes

Accounting invariant is validated twice on purpose: here at the edge (422 with
a clear message) and again in LedgerService so seed scripts and jobs cannot
bypass it.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from reckonflow.schemas.common import CurrencyCode, MoneyStr


class LedgerLineCreate(BaseModel):
    """One debit-or-credit line inside a proposed transaction"""

    account_id: int = Field(..., examples=[1])
    debit: MoneyStr = Field("0", examples=["120.50"])
    credit: MoneyStr = Field("0", examples=["0"])
    currency: CurrencyCode = "EUR"
    memo: str | None = Field(None, max_length=500, examples=["Hotel Berlin"])

    @model_validator(mode="after")
    def check_single_sided(self) -> LedgerLineCreate:
        """Reject lines that are both debit and credit, or neither

        A line touching both sides hides money direction; a zero-zero line is
        noise that would still pass the balance check.
        """
        debit = Decimal(self.debit)
        credit = Decimal(self.credit)
        if debit < 0 or credit < 0:
            raise ValueError("I refuse negative amounts; flip the side instead")
        if debit > 0 and credit > 0:
            raise ValueError("A line is either a debit or a credit, not both")
        if debit == 0 and credit == 0:
            raise ValueError("A line must carry a non-zero debit or credit")
        return self


class LedgerTransactionCreate(BaseModel):
    """Whole transaction — the only unit that may be written"""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "reference": "TRV-2026-0001",
                    "description": "Hotel Berlin paid by company card",
                    "lines": [
                        {"account_id": 1, "debit": "420.00", "currency": "EUR"},
                        {"account_id": 2, "credit": "420.00", "currency": "EUR"},
                    ],
                }
            ]
        }
    )

    reference: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique business reference for spotting re-posts",
        examples=["TRV-2026-0001"],
    )
    description: str = Field(..., min_length=1, max_length=255)
    lines: list[LedgerLineCreate] = Field(..., min_length=2)

    @model_validator(mode="after")
    def check_balanced(self) -> LedgerTransactionCreate:
        """Enforce sum(debit) == sum(credit) before the request reaches the DB"""
        total_debit = sum((Decimal(line.debit) for line in self.lines), Decimal("0"))
        total_credit = sum((Decimal(line.credit) for line in self.lines), Decimal("0"))
        if total_debit != total_credit:
            raise ValueError(
                f"Unbalanced transaction: debit={total_debit} credit={total_credit}"
            )
        return self


class LedgerEntryRead(BaseModel):
    """One persisted ledger line"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    debit: MoneyStr
    credit: MoneyStr
    currency: str
    memo: str | None = None


class LedgerTransactionRead(BaseModel):
    """Persisted transaction with its entries"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    description: str
    created_at: datetime
    entries: list[LedgerEntryRead] = Field(default_factory=list)
