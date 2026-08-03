"""Provider boundary for receipt extraction

Everything above this line talks to ReceiptExtractor and knows nothing about
Groq, PydanticAI, or HTTP. That lets CI run the full receipt flow with a
deterministic stub and swap providers later without touching the domain.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from reckonflow.schemas.receipt import ReceiptExtraction


class ExtractionError(RuntimeError):
    """Extraction failed for a reason worth showing the user"""


@runtime_checkable
class ReceiptExtractor(Protocol):
    """Anything that turns receipt text into a validated structure"""

    @property
    def name(self) -> str:
        """Implementation name for logs and eval reports"""
        ...

    async def extract(self, *, raw_text: str, filename: str) -> ReceiptExtraction:
        """Structured receipt data, or ExtractionError on failure"""
        ...
