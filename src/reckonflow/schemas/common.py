"""Shared schema building blocks

MoneyStr is the important one: money crosses the wire as a JSON string because
JSON numbers are IEEE-754 doubles in most clients, and a double silently turns
0.1 into 0.1000000000000000055 — unacceptable in a ledger.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field

from reckonflow.core.money import money_to_str


def _coerce_money(value: Any) -> Any:
    """Coerce Decimal/int/str to an exact string for Pydantic

    Float is rejected outright — by the time a float arrives, rounding error
    already happened and cannot be undone.
    """
    if isinstance(value, bool):
        raise ValueError("Refuse booleans as money values")
    if isinstance(value, float):
        raise ValueError("Refuse float money values; send a JSON string instead")
    if isinstance(value, Decimal):
        return money_to_str(value)
    if isinstance(value, int):
        return str(value)
    return value


def _must_be_decimal(value: str) -> str:
    """Fail fast on strings Decimal cannot parse, before they reach the DB"""
    try:
        Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{value!r} is not a valid decimal amount") from exc
    return value


MoneyStr = Annotated[
    str,
    BeforeValidator(_coerce_money),
    AfterValidator(_must_be_decimal),
    Field(examples=["120.50"]),
]

CurrencyCode = Annotated[
    str,
    Field(min_length=3, max_length=3, examples=["EUR"]),
    AfterValidator(lambda code: code.upper()),
]


class ErrorResponse(BaseModel):
    """JSON body for handled domain errors"""

    error: str = Field(..., examples=["UnbalancedLedgerError"])
    detail: str = Field(..., examples=["Unbalanced transaction: debit=10 credit=9"])


def to_decimal(value: str) -> Decimal:
    """Convert validated MoneyStr back to Decimal for the service layer"""
    return Decimal(value)
