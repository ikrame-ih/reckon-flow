"""Store uploaded receipts and record extraction results

Bytes live on disk; Postgres only keeps a path. Large attachments do not
belong in the database — backups and migrations stay lighter that way
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from reckonflow.core.config import get_settings
from reckonflow.core.exceptions import ConflictError, NotFoundError
from reckonflow.models import Expense, Receipt
from reckonflow.models.travel import ReceiptStatus
from reckonflow.schemas.receipt import ReceiptExtraction

# Strip path separators and odd characters so names like ../../etc/passwd
# cannot escape the storage directory when joined
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
MAX_EXTRACTION_CHARS = 50_000


def safe_filename(name: str) -> str:
    """Reduce an upload name to a safe basename before joining onto a path"""
    cleaned = _SAFE_NAME_RE.sub("_", Path(name).name).strip("._") or "receipt"
    return cleaned[:120]


class ReceiptService:
    """Persist uploads and drive extraction status through its lifecycle"""

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
        """Insert the row, then write bytes so a failed flush leaves no orphan"""
        if expense_id is not None:
            expense = await self._session.get(Expense, expense_id)
            if expense is None:
                raise NotFoundError(f"Expense {expense_id} not found")
            existing = await self._session.scalar(
                select(Receipt.id).where(Receipt.expense_id == expense_id)
            )
            if existing is not None:
                raise ConflictError(
                    f"Expense {expense_id} already has a receipt (id={existing})"
                )

        self._storage.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}_{safe_filename(filename)}"
        path = self._resolve_storage_path(self._storage / stored_name)

        receipt = Receipt(
            expense_id=expense_id,
            filename=safe_filename(filename),
            content_type=content_type or "application/octet-stream",
            storage_path=str(path),
            status=ReceiptStatus.UPLOADED,
        )
        self._session.add(receipt)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(f"Expense {expense_id} already has a receipt") from exc

        try:
            path.write_bytes(content)
        except Exception:
            # Roll back the row if the filesystem write fails
            await self._session.rollback()
            raise
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
        """Persist validated extraction JSON beside the file path

        JSON keeps the LLM contract intact and auditable; normalizing into
        columns would freeze a schema that still evolves
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

    def _resolve_storage_path(self, path: Path) -> Path:
        """Refuse any path that escapes the configured storage directory"""
        storage_root = self._storage.resolve()
        resolved = path.resolve()
        if not resolved.is_relative_to(storage_root):
            raise NotFoundError("Stored file path escapes the storage directory")
        return resolved

    def read_extraction(self, receipt: Receipt) -> ReceiptExtraction | None:
        """Re-validate stored JSON on the way out — never trust the column blindly"""
        if not receipt.extracted_json:
            return None
        try:
            return ReceiptExtraction.model_validate(json.loads(receipt.extracted_json))
        except Exception:
            return None

    def read_text(self, receipt: Receipt) -> str:
        """Read stored bytes as text for extraction (plain text / OCR output only)"""
        path = self._resolve_storage_path(Path(receipt.storage_path))
        if not path.exists():
            raise NotFoundError(f"Stored file for receipt {receipt.id} is missing")
        text = path.read_bytes().decode("utf-8", errors="replace")
        if len(text) > MAX_EXTRACTION_CHARS:
            return text[:MAX_EXTRACTION_CHARS]
        return text
