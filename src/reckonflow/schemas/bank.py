"""Bank statement shapes and the CSV row contract

Every CSV row is validated with Pydantic — bank exports are external input with
mixed date formats, comma decimals, and the occasional bad row that must not
abort the whole import.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from reckonflow.schemas.common import CurrencyCode, MoneyStr

# Date formats seen in real exports, most specific first
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%m/%d/%Y")


class BankCsvRow(BaseModel):
    """One validated row from an uploaded bank CSV"""

    model_config = ConfigDict(extra="ignore")

    booking_date: date
    amount: MoneyStr
    currency: CurrencyCode = "EUR"
    description: str = Field(..., min_length=1)
    external_id: str | None = Field(None, max_length=64)

    @field_validator("booking_date", mode="before")
    @classmethod
    def parse_date(cls, value: Any) -> Any:
        """Try each known layout instead of forcing banks to speak ISO"""
        if not isinstance(value, str):
            return value
        text = value.strip()
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Cannot read {value!r} as a date")

    @field_validator("amount", mode="before")
    @classmethod
    def normalize_amount(cls, value: Any) -> Any:
        """Strip thousands separators and normalize European decimal commas"""
        if not isinstance(value, str):
            return value
        text = value.strip().replace(" ", "").replace("\u00a0", "")
        if "," in text and "." in text:
            # "1.234,56" -> the comma is the decimal separator
            text = text.replace(".", "").replace(",", ".")
        elif "," in text:
            text = text.replace(",", ".")
        return text

    @field_validator("external_id", mode="before")
    @classmethod
    def blank_to_none(cls, value: Any) -> Any:
        """Treat an empty CSV cell as absent, not as an empty identifier"""
        if isinstance(value, str) and not value.strip():
            return None
        return value


class BankTransactionRead(BaseModel):
    """Stored bank line"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_date: date
    amount: MoneyStr
    currency: str
    description: str
    external_id: str | None = None
    match_status: str
    matched_expense_id: int | None = None
    created_at: datetime


class BankImportError(BaseModel):
    """One rejected import row so the uploader can fix the source file"""

    line_number: int = Field(..., description="1-based row number in the CSV body")
    reason: str


class BankImportResult(BaseModel):
    """Import summary: inserted, duplicates skipped, and row-level errors"""

    received_rows: int
    inserted: int
    skipped_duplicates: int
    errors: list[BankImportError] = Field(default_factory=list)
