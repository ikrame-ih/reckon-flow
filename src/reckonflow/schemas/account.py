"""I define the account request/response shapes

Accounts are the buckets ledger entries debit and credit, so I keep them
deliberately boring: a stable code, a human name, and a currency
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from reckonflow.schemas.common import CurrencyCode, MoneyStr


class AccountCreate(BaseModel):
    """I validate the payload that opens a new ledger account"""

    code: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Stable short code I use in imports and demos",
        examples=["6400"],
    )
    name: str = Field(..., min_length=1, max_length=120, examples=["Travel expenses"])
    currency: CurrencyCode = "EUR"


class AccountRead(BaseModel):
    """I describe an account as the API returns it"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., examples=[1])
    code: str = Field(..., examples=["6400"])
    name: str = Field(..., examples=["Travel expenses"])
    currency: str = Field(..., examples=["EUR"])
    created_at: datetime


class AccountBalanceRead(BaseModel):
    """I report a balance computed by aggregation, never from a stored column"""

    account_id: int = Field(..., examples=[1])
    code: str = Field(..., examples=["6400"])
    currency: str = Field(..., examples=["EUR"])
    balance: MoneyStr = Field(
        ...,
        description="SUM(debit) - SUM(credit) over every entry on this account",
        examples=["1250.0000"],
    )
