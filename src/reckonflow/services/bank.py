"""Import bank statement CSVs into normalized rows

A statement export is untrusted input — validate every row with Pydantic and
collect failures instead of aborting. One bad line in a 900-row file should
not void the entire import.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reckonflow.models import BankTransaction
from reckonflow.schemas.bank import BankCsvRow, BankImportError, BankImportResult

# Map header spellings from real exports onto canonical field names
_HEADER_ALIASES: dict[str, str] = {
    "date": "booking_date",
    "booking date": "booking_date",
    "booking_date": "booking_date",
    "value date": "booking_date",
    "amount": "amount",
    "value": "amount",
    "currency": "currency",
    "ccy": "currency",
    "description": "description",
    "details": "description",
    "reference": "description",
    "external_id": "external_id",
    "external id": "external_id",
    "transaction id": "external_id",
    "id": "external_id",
}


def normalize_header(name: str) -> str:
    """Fold a CSV header onto a canonical field name"""
    key = name.strip().lower().lstrip("\ufeff")
    return _HEADER_ALIASES.get(key, key.replace(" ", "_"))


class BankService:
    """Ingest bank CSVs and query stored transactions"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def import_csv(self, content: bytes) -> BankImportResult:
        """Parse, validate, and bulk-insert a CSV statement

        Dedupe on external_id when present — re-uploading yesterday's file is
        the most common operator mistake.
        """
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            no_header = BankImportError(line_number=0, reason="The file has no header")
            return BankImportResult(
                received_rows=0,
                inserted=0,
                skipped_duplicates=0,
                errors=[no_header],
            )
        reader.fieldnames = [normalize_header(name) for name in reader.fieldnames]

        parsed: list[BankCsvRow] = []
        errors: list[BankImportError] = []
        received = 0

        for line_number, raw in enumerate(reader, start=1):
            if not any((value or "").strip() for value in raw.values()):
                continue  # blank trailing lines are harmless noise
            received += 1
            try:
                parsed.append(BankCsvRow.model_validate(raw))
            except Exception as exc:
                errors.append(BankImportError(line_number=line_number, reason=str(exc)))

        existing_ids = await self._existing_external_ids(
            [row.external_id for row in parsed if row.external_id]
        )

        inserted = 0
        skipped = 0
        seen_in_file: set[str] = set()
        for row in parsed:
            key = row.external_id
            if key and (key in existing_ids or key in seen_in_file):
                skipped += 1
                continue
            if key:
                seen_in_file.add(key)
            self._session.add(
                BankTransaction(
                    booking_date=row.booking_date,
                    amount=Decimal(row.amount),
                    currency=row.currency,
                    description=row.description,
                    external_id=row.external_id,
                )
            )
            inserted += 1

        await self._session.flush()
        return BankImportResult(
            received_rows=received,
            inserted=inserted,
            skipped_duplicates=skipped,
            errors=errors,
        )

    async def _existing_external_ids(self, candidates: list[str]) -> set[str]:
        """Load existing external ids in one query before deduping"""
        if not candidates:
            return set()
        stmt = select(BankTransaction.external_id).where(
            BankTransaction.external_id.in_(candidates)
        )
        result = await self._session.execute(stmt)
        return {value for value in result.scalars().all() if value is not None}

    async def list_transactions(
        self, *, match_status: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[BankTransaction]:
        stmt = (
            select(BankTransaction)
            .order_by(BankTransaction.booking_date.desc(), BankTransaction.id.desc())
            .limit(limit)
            .offset(offset)
        )
        if match_status is not None:
            stmt = stmt.where(BankTransaction.match_status == match_status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
