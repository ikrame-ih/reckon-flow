"""Receipt extraction after upload — ARQ job or BackgroundTasks fallback

Opens its own DB session — the request-scoped session is closed before
the job runs. Failures land on the receipt row; each attempt is an
extraction_runs row (latency, provider, error). Token counts are null
until a provider exposes them.
"""

from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession

from reckonflow.ai import ReceiptExtractor, get_receipt_extractor
from reckonflow.core.db import SessionLocal
from reckonflow.core.logging import get_logger
from reckonflow.models import ExtractionRun
from reckonflow.models.travel import ReceiptStatus
from reckonflow.services.receipts import ReceiptService

logger = get_logger(__name__)


async def extract_receipt_task(
    receipt_id: int,
    *,
    extractor: ReceiptExtractor | None = None,
    attempt: int = 1,
    job_id: str | None = None,
    reraise: bool = False,
) -> None:
    """Open a private session and extract one receipt"""
    async with SessionLocal() as session:
        await run_extraction(
            session,
            receipt_id,
            extractor=extractor,
            attempt=attempt,
            job_id=job_id,
            reraise=reraise,
        )


async def run_extraction(
    session: AsyncSession,
    receipt_id: int,
    *,
    extractor: ReceiptExtractor | None = None,
    attempt: int = 1,
    job_id: str | None = None,
    reraise: bool = False,
) -> None:
    """Extract one receipt and persist structured output

    Never raises when reraise is False (inline BackgroundTasks).
    When reraise is True (ARQ), a failure is recorded then raised so the
    worker can retry.
    """
    extractor = extractor or get_receipt_extractor()
    started = time.perf_counter()
    provider = getattr(extractor, "name", type(extractor).__name__)
    service = ReceiptService(session)

    try:
        receipt = await service.get_receipt(receipt_id)
        if receipt.status == ReceiptStatus.EXTRACTED:
            logger.info("receipt.already_extracted", receipt_id=receipt_id)
            return
        await service.mark_processing(receipt_id)
        await session.commit()
        receipt = await service.get_receipt(receipt_id)
    except Exception as exc:
        await session.rollback()
        logger.warning(
            "receipt.task_start_failed", receipt_id=receipt_id, error=str(exc)
        )
        if reraise:
            raise
        return

    outcome = "failed"
    error_text: str | None = None
    try:
        raw_text = service.read_text(receipt)
        extraction = await extractor.extract(
            raw_text=raw_text, filename=receipt.filename
        )
        await service.save_extraction(receipt_id, extraction)
        await session.commit()
        outcome = "success"
        logger.info(
            "receipt.extracted",
            receipt_id=receipt_id,
            provider=provider,
            vendor=extraction.vendor,
        )
    except Exception as exc:
        await session.rollback()
        error_text = str(exc)
        await service.mark_failed(receipt_id, error_text)
        await session.commit()
        logger.warning(
            "receipt.extraction_failed", receipt_id=receipt_id, error=error_text
        )

    duration_ms = int((time.perf_counter() - started) * 1000)
    session.add(
        ExtractionRun(
            receipt_id=receipt_id,
            provider=provider,
            outcome=outcome,
            duration_ms=duration_ms,
            attempt=attempt,
            job_id=job_id,
            error=error_text[:2000] if error_text else None,
            token_count=None,
        )
    )
    await session.commit()
    logger.info(
        "receipt.extraction_run",
        receipt_id=receipt_id,
        outcome=outcome,
        duration_ms=duration_ms,
        attempt=attempt,
        provider=provider,
    )
    if reraise and outcome == "failed":
        raise RuntimeError(error_text or "extraction failed")
