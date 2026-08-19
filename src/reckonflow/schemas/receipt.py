"""Receipt request/response shapes and the strict LLM extraction contract

ReceiptExtraction is the only structure the model may produce. Fields carry
data, never instructions — no field can name an account, approve a request, or
trigger a payment, so prompt injection in receipt text has nothing to hook into.
See docs/adr/002-receipt-untrusted-input.md
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from reckonflow.models.travel import ReceiptStatus
from reckonflow.schemas.common import CurrencyCode, MoneyStr


class ReceiptLineItem(BaseModel):
    """One purchased line on a receipt"""

    # extra="forbid" — invented fields fail validation instead of slipping into the DB
    model_config = ConfigDict(extra="forbid")

    description: str = Field(..., max_length=300, examples=["Room, 3 nights"])
    quantity: MoneyStr = Field("1", examples=["3"])
    unit_price: MoneyStr | None = Field(None, examples=["180.00"])
    total: MoneyStr = Field(..., examples=["540.00"])


class ReceiptExtraction(BaseModel):
    """Structured result of reading a receipt — plain values the ledger can reconcile"""

    model_config = ConfigDict(extra="forbid")

    vendor: str = Field(..., max_length=160, examples=["Hotel Adlon"])
    receipt_date: date | None = Field(None, examples=["2026-09-17"])
    currency: CurrencyCode = Field("EUR", examples=["EUR"])
    subtotal: MoneyStr | None = Field(None, examples=["540.00"])
    vat_amount: MoneyStr | None = Field(None, examples=["72.40"])
    vat_rate: MoneyStr | None = Field(
        None, description="VAT percentage as written on the receipt", examples=["19"]
    )
    total: MoneyStr = Field(..., examples=["612.40"])
    line_items: list[ReceiptLineItem] = Field(default_factory=list)


class ReceiptRead(BaseModel):
    """Stored receipt and where it stands in the extraction pipeline"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    expense_id: int | None = None
    filename: str
    content_type: str
    status: ReceiptStatus
    error_message: str | None = None
    created_at: datetime


class ReceiptAccepted(BaseModel):
    """Upload acknowledged before extraction runs

    202 rather than 200 because the LLM call happens after the response — an
    upload must not block on a third-party rate limit.
    """

    receipt_id: int
    status: ReceiptStatus = ReceiptStatus.UPLOADED
    poll_url: str = Field(..., examples=["/api/v1/receipts/1"])
    queue: str = Field(
        "inline",
        description="arq when Redis job queued; inline when BackgroundTasks fallback",
        examples=["arq", "inline"],
    )


class ExtractionRunRead(BaseModel):
    """One extraction attempt for tracing — tokens are null on the stub"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_id: int
    provider: str
    outcome: str
    duration_ms: int
    attempt: int
    job_id: str | None = None
    error: str | None = None
    token_count: int | None = None
    created_at: datetime


class ReceiptExtractionRead(BaseModel):
    """Extraction payload once background processing finishes"""

    receipt_id: int
    status: ReceiptStatus
    extraction: ReceiptExtraction | None = None
    error_message: str | None = None
