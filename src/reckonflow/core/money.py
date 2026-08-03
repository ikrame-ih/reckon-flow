"""I convert money amounts to Decimal without float contamination

I always build Decimal from str or int so binary rounding cannot enter the ledger
"""

from decimal import Decimal, InvalidOperation


def parse_money(value: str | int | Decimal) -> Decimal:
    """I turn a money value into an exact Decimal

    I reject float on purpose — float already carries binary error
    """
    if isinstance(value, float):
        raise TypeError("I refuse float money values; pass str, int, or Decimal")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"I cannot parse money from {value!r}") from exc


def money_to_str(value: Decimal) -> str:
    """I serialize Decimal for JSON so clients never see a float"""
    return format(value, "f")
