"""ORM models for travel, approvals, expenses, receipts, and bank lines"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from reckonflow.models.base import Base
from reckonflow.models.types import EmbeddingVector


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"


class ReceiptStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    FAILED = "failed"


class MatchStatus(StrEnum):
    UNMATCHED = "unmatched"
    SUGGESTED = "suggested"
    MATCHED = "matched"
    PENDING_REVIEW = "pending_review"


class TravelRequest(Base):
    """Trip pre-request before money is spent"""

    __tablename__ = "travel_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_name: Mapped[str] = mapped_column(String(120))
    destination: Mapped[str] = mapped_column(String(120))
    purpose: Mapped[str] = mapped_column(Text)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    estimated_amount: Mapped[Decimal] = mapped_column(Numeric(15, 4))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    approval: Mapped[Approval | None] = relationship(
        back_populates="travel_request", uselist=False
    )
    expenses: Mapped[list[Expense]] = relationship(back_populates="travel_request")


class Approval(Base):
    """pending → approved/rejected → paid state machine"""

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    travel_request_id: Mapped[int] = mapped_column(
        ForeignKey("travel_requests.id"), unique=True
    )
    status: Mapped[str] = mapped_column(String(32), default=ApprovalStatus.PENDING)
    reviewer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    travel_request: Mapped[TravelRequest] = relationship(back_populates="approval")


class Expense(Base):
    """Spend that may later match a bank line and a receipt"""

    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    travel_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("travel_requests.id"), nullable=True, index=True
    )
    vendor: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 4))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    expense_date: Mapped[date] = mapped_column(Date)
    match_status: Mapped[str] = mapped_column(String(32), default=MatchStatus.UNMATCHED)
    # Cache description embedding so reconciliation does not re-embed every request
    embedding: Mapped[list[float] | None] = mapped_column(
        EmbeddingVector(), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    travel_request: Mapped[TravelRequest | None] = relationship(
        back_populates="expenses"
    )
    receipt: Mapped[Receipt | None] = relationship(
        back_populates="expense", uselist=False
    )
    bank_match: Mapped[BankTransaction | None] = relationship(
        back_populates="matched_expense",
        uselist=False,
        foreign_keys="BankTransaction.matched_expense_id",
    )


class Receipt(Base):
    """Uploaded receipt file and optional structured extraction"""

    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int | None] = mapped_column(
        ForeignKey("expenses.id"), nullable=True, unique=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    storage_path: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default=ReceiptStatus.UPLOADED)
    extracted_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    expense: Mapped[Expense | None] = relationship(back_populates="receipt")
    extraction_runs: Mapped[list[ExtractionRun]] = relationship(
        back_populates="receipt"
    )


class ExtractionRun(Base):
    """One extraction attempt — latency and outcome, not a dashboard product"""

    __tablename__ = "extraction_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(
        ForeignKey("receipts.id"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(32))
    duration_ms: Mapped[int] = mapped_column()
    attempt: Mapped[int] = mapped_column(default=1)
    job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_count: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    receipt: Mapped[Receipt] = relationship(back_populates="extraction_runs")


class BankTransaction(Base):
    """One normalized bank CSV row ready for reconciliation"""

    __tablename__ = "bank_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 4))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    description: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    match_status: Mapped[str] = mapped_column(String(32), default=MatchStatus.UNMATCHED)
    matched_expense_id: Mapped[int | None] = mapped_column(
        ForeignKey("expenses.id"), nullable=True, unique=True
    )
    # Embeddings optional — amount, date, and RapidFuzz suffice; vectors sharpen ranks
    embedding: Mapped[list[float] | None] = mapped_column(
        EmbeddingVector(), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    matched_expense: Mapped[Expense | None] = relationship(
        back_populates="bank_match", foreign_keys=[matched_expense_id]
    )
