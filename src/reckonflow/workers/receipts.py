"""Optional arq worker entrypoint for durable receipt extraction

Default deploy still uses FastAPI BackgroundTasks (see ADR 005). Run this
worker only when you want Redis-backed retries:

  uv add arq
  uv run arq reckonflow.workers.receipts.WorkerSettings
"""

from __future__ import annotations

from reckonflow.core.config import get_settings
from reckonflow.tasks.receipts import extract_receipt_task


async def extract_receipt(ctx: dict[str, object], receipt_id: int) -> None:
    """arq job wrapper around the existing extraction task"""
    await extract_receipt_task(receipt_id)


class WorkerSettings:
    """Minimal arq settings — install arq before importing this module in prod"""

    functions = [extract_receipt]
    redis_settings = None  # set from REDIS_URL when enabling the worker

    @staticmethod
    def on_startup(ctx: dict[str, object]) -> None:
        settings = get_settings()
        ctx["settings"] = settings
