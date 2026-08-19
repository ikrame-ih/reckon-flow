"""ARQ worker settings — run: uv run arq reckonflow.worker.WorkerSettings"""

from __future__ import annotations

from typing import Any

from reckonflow.core.config import get_settings
from reckonflow.tasks.receipts import extract_receipt_task
from reckonflow.worker_queue import _redis_settings, arq_queue_name


async def extract_receipt(ctx: dict[str, Any], receipt_id: int) -> str:
    """Durable job: retry on raise; skip if the row is already extracted"""
    attempt = int(ctx.get("job_try") or 1)
    job_id = str(ctx.get("job_id") or "")
    await extract_receipt_task(
        receipt_id, attempt=attempt, job_id=job_id or None, reraise=True
    )
    return "ok"


class WorkerSettings:
    """ARQ discovers this class by dotted path"""

    functions = [extract_receipt]
    redis_settings = None
    job_timeout = 120
    max_tries = 3
    keep_result_s = 3600
    queue_name = "reckonflow:arq"


def _bind_settings() -> None:
    settings = get_settings()
    WorkerSettings.redis_settings = _redis_settings()
    WorkerSettings.job_timeout = settings.receipt_job_timeout_seconds
    WorkerSettings.max_tries = settings.receipt_job_max_tries
    WorkerSettings.queue_name = arq_queue_name()


_bind_settings()
