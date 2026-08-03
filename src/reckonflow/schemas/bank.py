"""I define bank statement shapes, including the CSV row contract

I validate every CSV row with Pydantic rather than trusting the file, because
a bank export is external input: dates come in three formats, amounts arrive
with commas, and a single bad row must not abort the whole import
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from reckonflow.schemas.common import CurrencyCode, MoneyStr

# I accept the formats real exports actually use, most specific first
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%m/%d/%Y")


class BankCsvRow(BaseModel):
    """I am one validated row of an uploaded bank CSV"""

    model_config = ConfigDict(extra="ignore")

    booking_date: date
    amount: MoneyStr
    currency: CurrencyCode = "EUR"
    description: str = Field(..., min_length=1)
    external_id: str | None = Field(None, max_length=64)

    @field_validator("booking_date", mode="before")
    @classmethod
    def parse_date(cls, value: Any) -> Any:
        """I try each known layout instead of forcing banks to speak ISO"""
        if not isinstance(value, str):
            return value
        text = value.strip()
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"I cannot read {value!r} as a date")

    @field_validator("amount", mode="before")
    @classmethod
    def normalize_amount(cls, value: Any) -> Any:
        """I strip thousands separators and convert the European decimal comma"""
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
        """I treat an empty CSV cell as absent, not as an empty identifier"""
        if isinstance(value, str) and not value.strip():
            return None
        return value


class BankTransactionRead(BaseModel):
    """I describe a stored bank line"""

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
    """I report a rejected row so the uploader can fix the source file"""

    line_number: int = Field(..., description="1-based row number in the CSV body")
    reason: str


class BankImportResult(BaseModel):
    """I summarize an import: what landed, what was a duplicate, what failed"""

    received_rows: int
    inserted: int
    skipped_duplicates: int
    errors: list[BankImportError] = Field(default_factory=list)
