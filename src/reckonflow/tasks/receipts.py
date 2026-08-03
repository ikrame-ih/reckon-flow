"""I run receipt extraction after the response has already been sent

The task opens its own database session on purpose: the request-scoped session
is closed by the time FastAPI runs background tasks, so reusing it would fail
at the first query

This is a BackgroundTask, not a queue. It is honest for a portfolio demo and
it survives a restart badly — the upgrade path is Celery or arq, and nothing
above this function would change
"""

from __future__ import annotations

from reckonflow.ai import ReceiptExtractor, get_receipt_extractor
from reckonflow.core.db import SessionLocal
from reckonflow.core.logging import get_logger
from reckonflow.services.receipts import ReceiptService

logger = get_logger(__name__)


async def extract_receipt_task(
    receipt_id: int, *, extractor: ReceiptExtractor | None = None
) -> None:
    """I read one uploaded receipt and store its structured extraction

    I never raise: a failure here must land in the receipt row as `failed`
    with a reason, not in an unhandled task exception nobody sees
    """
    extractor = extractor or get_receipt_extractor()

    async with SessionLocal() as session:
        service = ReceiptService(session)
        try:
            receipt = await service.mark_processing(receipt_id)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.warning(
                "receipt.task_start_failed", receipt_id=receipt_id, error=str(exc)
            )
            return

        try:
            raw_text = service.read_text(receipt)
            extraction = await extractor.extract(
                raw_text=raw_text, filename=receipt.filename
            )
        except Exception as exc:
            # I catch broadly because a provider SDK can raise anything, and
            # the user still deserves a readable reason on the receipt row
            await session.rollback()
            await service.mark_failed(receipt_id, str(exc))
            await session.commit()
            logger.warning(
                "receipt.extraction_failed", receipt_id=receipt_id, error=str(exc)
            )
            return

        await service.save_extraction(receipt_id, extraction)
        await session.commit()
        logger.info(
            "receipt.extracted",
            receipt_id=receipt_id,
            provider=extractor.name,
            vendor=extraction.vendor,
        )
