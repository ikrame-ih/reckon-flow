"""Background receipt extraction after the HTTP response is sent

Opens its own DB session — the request-scoped session is closed before
BackgroundTasks run. This is not a queue (honest for a demo); upgrade path is
Celery or arq without changing callers.
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
    """Extract one receipt and persist structured output

    Never raises — failures land on the receipt row as `failed` with a reason.
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
            # Broad catch — SDKs raise varied types; store readable reason on row
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
