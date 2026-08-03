"""I import bank statement CSVs into normalized rows

An uploaded statement is untrusted input, so I validate every row with
Pydantic and collect failures instead of aborting: one malformed line in a
900-line export should not cost the user the whole import
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reckonflow.models import BankTransaction
from reckonflow.schemas.bank import BankCsvRow, BankImportError, BankImportResult

# I map the header spellings I have actually seen onto my own field names
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
    """I fold a CSV header onto my canonical field name"""
    key = name.strip().lower().lstrip("\ufeff")
    return _HEADER_ALIASES.get(key, key.replace(" ", "_"))


class BankService:
    """I own bank statement ingestion and lookups"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def import_csv(self, content: bytes) -> BankImportResult:
        """I parse, validate, and bulk-insert a CSV statement

        I dedupe on external_id when the bank provides one, because re-uploading
        yesterday's file is the single most common operator mistake
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
                continue  # I skip blank trailing lines silently
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
        """I fetch the ids already stored so the dedupe costs one query"""
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
