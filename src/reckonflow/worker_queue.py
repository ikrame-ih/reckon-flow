"""Enqueue receipt extraction: ARQ when configured, else in-process.

Job id is `receipt-extract:{id}` so a retried POST cannot stack two jobs
for the same row. ARQ retries the function if it raises (see worker).
"""

from __future__ import annotations

from typing import Any

from reckonflow.core.config import get_settings
from reckonflow.core.logging import get_logger

logger = get_logger(__name__)

EXTRACT_RECEIPT_JOB = "extract_receipt"

_pool: Any = None


def arq_queue_name() -> str:
    prefix = get_settings().redis_key_prefix.rstrip(":")
    return f"{prefix}:arq"


def receipt_job_id(receipt_id: int) -> str:
    """Stable ARQ job id — enqueue with the same id is a no-op if still queued"""
    return f"receipt-extract:{receipt_id}"


def _redis_settings() -> Any:
    from arq.connections import RedisSettings

    return RedisSettings.from_dsn(get_settings().redis_url)


async def get_arq_pool() -> Any:
    """Process-wide ARQ pool (separate from the decode_responses app client)"""
    global _pool
    if _pool is None:
        from arq import create_pool

        _pool = await create_pool(_redis_settings())
    return _pool


async def close_arq_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def enqueue_extract(receipt_id: int) -> str:
    """Queue extraction. Returns 'arq' or 'inline' (caller runs BackgroundTasks)."""
    settings = get_settings()
    if settings.receipt_queue != "arq":
        return "inline"
    try:
        pool = await get_arq_pool()
        job = await pool.enqueue_job(
            EXTRACT_RECEIPT_JOB,
            receipt_id,
            _job_id=receipt_job_id(receipt_id),
            _queue_name=arq_queue_name(),
        )
        if job is None:
            logger.info("receipt.job_already_queued", receipt_id=receipt_id)
        else:
            logger.info("receipt.job_queued", receipt_id=receipt_id, job_id=job.job_id)
        return "arq"
    except Exception as exc:
        logger.warning(
            "receipt.arq_enqueue_failed",
            receipt_id=receipt_id,
            error=str(exc),
        )
        return "inline"
