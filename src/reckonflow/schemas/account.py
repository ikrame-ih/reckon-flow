"""Account request/response shapes

Accounts are the buckets ledger entries debit and credit — stable code, human
name, currency.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from reckonflow.schemas.common import CurrencyCode, MoneyStr


class AccountCreate(BaseModel):
    """Payload for opening a new ledger account"""

    code: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Stable short code used in imports and demos",
        examples=["6400"],
    )
    name: str = Field(..., min_length=1, max_length=120, examples=["Travel expenses"])
    currency: CurrencyCode = "EUR"


class AccountRead(BaseModel):
    """Account as returned by the API"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., examples=[1])
    code: str = Field(..., examples=["6400"])
    name: str = Field(..., examples=["Travel expenses"])
    currency: str = Field(..., examples=["EUR"])
    created_at: datetime


class AccountBalanceRead(BaseModel):
    """Balance from aggregation — never a stored column"""

    account_id: int = Field(..., examples=[1])
    code: str = Field(..., examples=["6400"])
    currency: str = Field(..., examples=["EUR"])
    balance: MoneyStr = Field(
        ...,
        description="SUM(debit) - SUM(credit) over every entry on this account",
        examples=["1250.0000"],
    )
