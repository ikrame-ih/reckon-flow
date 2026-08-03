"""I select the receipt extractor for the current environment

The rule is one line: a Groq key means the model runs, no key means the
deterministic stub runs. Nothing else in the codebase branches on that, so
tests, CI, and an offline demo all exercise the same code path
"""

from __future__ import annotations

from reckonflow.ai.base import ExtractionError, ReceiptExtractor
from reckonflow.ai.stub import StubReceiptExtractor
from reckonflow.core.config import get_settings
from reckonflow.core.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "ExtractionError",
    "ReceiptExtractor",
    "StubReceiptExtractor",
    "get_receipt_extractor",
]


def get_receipt_extractor() -> ReceiptExtractor:
    """I return the best extractor I can build without failing"""
    settings = get_settings()
    if not settings.groq_api_key:
        logger.info("receipt.extractor_selected", provider="stub", reason="no api key")
        return StubReceiptExtractor()

    try:
        from reckonflow.ai.groq_provider import build_groq_extractor

        extractor = build_groq_extractor()
    except Exception as exc:
        # A missing optional dependency must not take receipts offline; the
        # stub keeps the pipeline running and the log says why
        logger.warning("receipt.groq_unavailable", error=str(exc))
        return StubReceiptExtractor()

    logger.info(
        "receipt.extractor_selected", provider="groq", model=settings.groq_model
    )
    return extractor
