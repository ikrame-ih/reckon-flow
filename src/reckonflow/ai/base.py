"""I define the provider boundary for receipt extraction

Everything above this line — the endpoint, the background task, the evals —
talks to ReceiptExtractor and knows nothing about Groq, PydanticAI, or HTTP
That is what lets CI run the whole receipt flow with a deterministic stub, and
what will let me swap providers later without touching the domain
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from reckonflow.schemas.receipt import ReceiptExtraction


class ExtractionError(RuntimeError):
    """I signal that extraction failed for a reason worth showing the user"""


@runtime_checkable
class ReceiptExtractor(Protocol):
    """I am anything that can turn receipt text into a validated structure"""

    @property
    def name(self) -> str:
        """I identify the implementation in logs and eval reports"""
        ...

    async def extract(self, *, raw_text: str, filename: str) -> ReceiptExtraction:
        """I return structured receipt data, or raise ExtractionError"""
        ...
