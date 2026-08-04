"""Money helpers — refuse floats before they poison ledger math"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from reckonflow.core.money import money_to_str, parse_money
from reckonflow.schemas.common import MoneyStr


def test_parse_money_from_string_is_exact() -> None:
    assert parse_money("0.1") + parse_money("0.2") == Decimal("0.3")


def test_parse_money_accepts_int_and_decimal() -> None:
    assert parse_money(42) == Decimal("42")
    assert parse_money(Decimal("1.2345")) == Decimal("1.2345")


def test_parse_money_rejects_float() -> None:
    """A float has already lost precision, so casting it would hide the bug"""
    with pytest.raises(TypeError):
        parse_money(0.1)  # type: ignore[arg-type]


def test_parse_money_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_money("twelve euros")


def test_money_to_str_never_uses_scientific_notation() -> None:
    """money_to_str avoids scientific notation"""
    assert money_to_str(Decimal("0.0001")) == "0.0001"
    assert money_to_str(Decimal("1234567.8900")) == "1234567.8900"


class _Payload(BaseModel):
    amount: MoneyStr


def test_money_str_schema_accepts_decimal_and_string() -> None:
    assert _Payload(amount="10.50").amount == "10.50"
    assert _Payload.model_validate({"amount": Decimal("10.5000")}).amount == "10.5000"


def test_money_str_schema_rejects_float_and_text() -> None:
    with pytest.raises(ValidationError):
        _Payload.model_validate({"amount": 10.5})
    with pytest.raises(ValidationError):
        _Payload.model_validate({"amount": "ten"})
