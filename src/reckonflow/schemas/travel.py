"""I define travel request, approval, and expense shapes

Approvals are a state machine, so the API never accepts a free-text status:
it accepts a named *action* and lets the service decide whether it is legal
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from reckonflow.models.travel import ApprovalStatus
from reckonflow.schemas.common import CurrencyCode, MoneyStr


class TravelRequestCreate(BaseModel):
    """I validate a trip pre-request before any money is committed"""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "employee_name": "Ikrame Ibn Hayoun",
                    "destination": "Berlin",
                    "purpose": "Client onboarding workshop",
                    "start_date": "2026-09-14",
                    "end_date": "2026-09-17",
                    "estimated_amount": "980.00",
                    "currency": "EUR",
                }
            ]
        }
    )

    employee_name: str = Field(..., min_length=1, max_length=120)
    destination: str = Field(..., min_length=1, max_length=120)
    purpose: str = Field(..., min_length=1)
    start_date: date
    end_date: date
    estimated_amount: MoneyStr = Field(..., examples=["980.00"])
    currency: CurrencyCode = "EUR"

    @model_validator(mode="after")
    def check_dates(self) -> TravelRequestCreate:
        """I reject trips that end before they start — a data error, not a rule"""
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be earlier than start_date")
        return self


class ApprovalRead(BaseModel):
    """I describe the approval attached to a travel request"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    travel_request_id: int
    status: ApprovalStatus
    reviewer: str | None = None
    notes: str | None = None
    updated_at: datetime


class TravelRequestRead(BaseModel):
    """I describe a stored travel request and its current approval"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_name: str
    destination: str
    purpose: str
    start_date: date
    end_date: date
    estimated_amount: MoneyStr
    currency: str
    created_at: datetime
    approval: ApprovalRead | None = None


class ApprovalAction(StrEnum):
    """I name the transitions a reviewer may request

    I expose actions instead of target statuses so an invalid jump like
    pending -> paid is impossible to even express in the request body
    """

    APPROVE = "approve"
    REJECT = "reject"
    MARK_PAID = "mark_paid"


class ApprovalTransition(BaseModel):
    """I carry the reviewer's decision"""

    action: ApprovalAction = Field(..., examples=["approve"])
    reviewer: str | None = Field(None, max_length=120, examples=["finance.lead"])
    notes: str | None = Field(None, examples=["Within policy for a 3-night trip"])


class ExpenseCreate(BaseModel):
    """I validate a spend that may later match a bank line and a receipt"""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "travel_request_id": 1,
                    "vendor": "Hotel Adlon",
                    "description": "3 nights, Berlin",
                    "amount": "612.40",
                    "currency": "EUR",
                    "expense_date": "2026-09-17",
                }
            ]
        }
    )

    travel_request_id: int | None = None
    vendor: str = Field(..., min_length=1, max_length=160)
    description: str = Field(..., min_length=1)
    amount: MoneyStr = Field(..., examples=["612.40"])
    currency: CurrencyCode = "EUR"
    expense_date: date


class ExpenseRead(BaseModel):
    """I describe a stored expense and where it stands in reconciliation"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    travel_request_id: int | None = None
    vendor: str
    description: str
    amount: MoneyStr
    currency: str
    expense_date: date
    match_status: str
    created_at: datetime
