"""I define the reconciliation suggestion and confirmation shapes

I always return the per-signal scores next to the fused score, because a
finance reviewer needs to see *why* a line was suggested before accepting it
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from reckonflow.schemas.common import MoneyStr


class MatchSignals(BaseModel):
    """I expose each individual signal so the suggestion stays auditable"""

    fuzzy_score: float = Field(
        ..., description="RapidFuzz token_set_ratio, 0-100", examples=[87.5]
    )
    amount_score: float = Field(
        ..., description="1.0 when the amounts are identical", examples=[0.98]
    )
    date_score: float = Field(
        ..., description="1.0 when the dates are the same day", examples=[0.8]
    )
    embedding_score: float | None = Field(
        None, description="Cosine similarity, only when both embeddings exist"
    )


class MatchSuggestion(BaseModel):
    """I am one candidate bank line for an expense"""

    model_config = ConfigDict(from_attributes=True)

    bank_transaction_id: int
    booking_date: date
    amount: MoneyStr
    currency: str
    description: str
    rrf_score: float = Field(..., description="Raw reciprocal rank fusion score")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="RRF score normalized against the best score reachable",
        examples=[0.91],
    )
    auto_matchable: bool = Field(
        ..., description="True when confidence and text agreement clear the gates"
    )
    signals: MatchSignals


class MatchSuggestionResponse(BaseModel):
    """I wrap the suggestions with the expense they belong to"""

    expense_id: int
    expense_amount: MoneyStr
    expense_date: date
    candidates_considered: int = Field(
        ..., description="How many bank rows survived the SQL prefilter"
    )
    suggestions: list[MatchSuggestion] = Field(default_factory=list)


class MatchConfirm(BaseModel):
    """I carry the reviewer's choice of bank line for an expense"""

    bank_transaction_id: int = Field(..., examples=[42])


class MatchResult(BaseModel):
    """I report the outcome of linking an expense to a bank line"""

    expense_id: int
    bank_transaction_id: int
    match_status: str = Field(..., examples=["matched"])
