"""I convert money amounts to Decimal safely

I always build Decimal from str or int, never from float,
so binary rounding errors never enter the ledger
"""

from decimal import Decimal, InvalidOperation


def parse_money(value: str) -> Decimal:
    """I turn a money string into an exact Decimal

    Example: parse_money("10.99") -> Decimal("10.99")
    """
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"I cannot parse money from {value!r}") from exc
