"""Choose stub or Groq receipt extractor from environment

Groq key → model runs; no key → deterministic stub. Nothing else branches on
that, so tests, CI, and offline demos share one code path.
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
    """Pick stub or Groq extractor based on configuration"""
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
