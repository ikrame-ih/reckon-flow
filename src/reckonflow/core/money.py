"""Convert money amounts to Decimal without float contamination

Always build Decimal from str or int. Starting from a float would already
bake in binary rounding error before the ledger sees the value
"""

from decimal import Decimal, InvalidOperation


def parse_money(value: str | int | Decimal) -> Decimal:
    """Turn a money value into an exact Decimal

    Rejects float on purpose — pass str, int, or Decimal instead
    """
    if isinstance(value, float):
        raise TypeError("Refuse float money values; pass str, int, or Decimal")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Cannot parse money from {value!r}") from exc


def money_to_str(value: Decimal) -> str:
    """Serialize Decimal for JSON so clients never coerce it to a float"""
    return format(value, "f")
