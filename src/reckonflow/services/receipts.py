"""I store uploaded receipts and record what extraction produced

I keep the bytes on disk and only a path in the database. Receipts are
attachments, not relations: putting megabytes in Postgres makes every backup,
replica, and migration slower for no query benefit
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reckonflow.core.config import get_settings
from reckonflow.core.exceptions import NotFoundError
from reckonflow.models import Expense, Receipt
from reckonflow.models.travel import ReceiptStatus
from reckonflow.schemas.receipt import ReceiptExtraction

# I refuse anything outside this set in a filename, so a crafted upload name
# such as ../../etc/passwd cannot escape the storage directory
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str) -> str:
    """I reduce an uploaded name to something safe to join onto a path"""
    cleaned = _SAFE_NAME_RE.sub("_", Path(name).name).strip("._") or "receipt"
    return cleaned[:120]


class ReceiptService:
    """I own receipt persistence and the extraction status transitions"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._storage = Path(get_settings().receipt_storage_dir)

    async def store_upload(
        self,
        *,
        filename: str,
        content_type: str,
        content: bytes,
        expense_id: int | None = None,
    ) -> Receipt:
        """I write the file, then create the row that points at it"""
        if expense_id is not None:
            expense = await self._session.get(Expense, expense_id)
            if expense is None:
                raise NotFoundError(f"Expense {expense_id} not found")

        self._storage.mkdir(parents=True, exist_ok=True)
        # I prefix a uuid so two people uploading receipt.pdf never collide
        stored_name = f"{uuid.uuid4().hex}_{safe_filename(filename)}"
        path = self._storage / stored_name
        path.write_bytes(content)

        receipt = Receipt(
            expense_id=expense_id,
            filename=safe_filename(filename),
            content_type=content_type or "application/octet-stream",
            storage_path=str(path),
            status=ReceiptStatus.UPLOADED,
        )
        self._session.add(receipt)
        await self._session.flush()
        return receipt

    async def get_receipt(self, receipt_id: int) -> Receipt:
        receipt = await self._session.get(Receipt, receipt_id)
        if receipt is None:
            raise NotFoundError(f"Receipt {receipt_id} not found")
        return receipt

    async def list_receipts(self, *, limit: int = 100) -> list[Receipt]:
        stmt = select(Receipt).order_by(Receipt.id.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_processing(self, receipt_id: int) -> Receipt:
        receipt = await self.get_receipt(receipt_id)
        receipt.status = ReceiptStatus.PROCESSING
        await self._session.flush()
        return receipt

    async def save_extraction(
        self, receipt_id: int, extraction: ReceiptExtraction
    ) -> Receipt:
        """I store the validated extraction as JSON next to the file path

        I keep it as a JSON document rather than columns because the shape is
        the model's contract, and I want the raw result auditable as-is
        """
        receipt = await self.get_receipt(receipt_id)
        receipt.extracted_json = extraction.model_dump_json()
        receipt.error_message = None
        receipt.status = ReceiptStatus.EXTRACTED
        await self._session.flush()
        return receipt

    async def mark_failed(self, receipt_id: int, reason: str) -> Receipt:
        receipt = await self.get_receipt(receipt_id)
        receipt.status = ReceiptStatus.FAILED
        receipt.error_message = reason[:2000]
        await self._session.flush()
        return receipt

    def read_extraction(self, receipt: Receipt) -> ReceiptExtraction | None:
        """I re-validate stored JSON on the way out, never trusting the column"""
        if not receipt.extracted_json:
            return None
        try:
            return ReceiptExtraction.model_validate(json.loads(receipt.extracted_json))
        except Exception:
            return None

    @staticmethod
    def read_text(receipt: Receipt) -> str:
        """I read the stored bytes as text

        Today I only handle text-like receipts; a real OCR step (Tesseract or a
        vision model) plugs in here without changing anything downstream
        """
        path = Path(receipt.storage_path)
        if not path.exists():
            raise NotFoundError(f"Stored file for receipt {receipt.id} is missing")
        return path.read_bytes().decode("utf-8", errors="replace")
