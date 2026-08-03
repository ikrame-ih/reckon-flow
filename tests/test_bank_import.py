"""Bank CSV ingestion — real-world messy exports

Untrusted input: mixed date formats, European decimals, header aliases, re-uploads.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from reckonflow.models import BankTransaction
from reckonflow.services.bank import BankService, normalize_header

CLEAN_CSV = b"""booking_date,amount,currency,description,external_id
2026-09-18,612.40,EUR,HOTEL ADLON BERLIN,TX-1
2026-09-15,-240.00,EUR,LUFTHANSA LH1234,TX-2
"""


async def test_clean_file_imports_every_row(session: AsyncSession) -> None:
    result = await BankService(session).import_csv(CLEAN_CSV)

    assert result.received_rows == 2
    assert result.inserted == 2
    assert result.errors == []

    count = await session.scalar(select(func.count()).select_from(BankTransaction))
    assert count == 2


async def test_alternative_headers_are_mapped(session: AsyncSession) -> None:
    csv = b"Date,Value,CCY,Details,Transaction ID\n18/09/2026,612.40,EUR,HOTEL,TX-9\n"

    result = await BankService(session).import_csv(csv)

    assert result.inserted == 1
    row = await session.scalar(select(BankTransaction))
    assert row is not None
    assert row.description == "HOTEL"
    assert row.external_id == "TX-9"


async def test_european_formats_are_understood(session: AsyncSession) -> None:
    """1.234,56 on 18.09.2026 is a perfectly normal German statement line"""
    csv = b'booking_date,amount,description\n18.09.2026,"1.234,56",HOTEL ADLON\n'

    result = await BankService(session).import_csv(csv)

    assert result.inserted == 1
    row = await session.scalar(select(BankTransaction))
    assert row is not None
    assert Decimal(row.amount) == Decimal("1234.56")
    assert row.booking_date.month == 9


async def test_one_bad_row_does_not_lose_the_good_ones(
    session: AsyncSession,
) -> None:
    """Aborting a 900-line import over one typo is the wrong failure mode"""
    csv = (
        b"booking_date,amount,description\n"
        b"2026-09-18,612.40,HOTEL ADLON\n"
        b"not-a-date,10.00,BROKEN ROW\n"
        b"2026-09-19,25.00,TAXI\n"
    )

    result = await BankService(session).import_csv(csv)

    assert result.inserted == 2
    assert len(result.errors) == 1
    assert result.errors[0].line_number == 2


async def test_reupload_is_deduped_by_external_id(session: AsyncSession) -> None:
    """Re-uploading yesterday's file is the most common operator mistake"""
    service = BankService(session)
    await service.import_csv(CLEAN_CSV)

    result = await service.import_csv(CLEAN_CSV)

    assert result.inserted == 0
    assert result.skipped_duplicates == 2

    count = await session.scalar(select(func.count()).select_from(BankTransaction))
    assert count == 2


async def test_duplicates_inside_one_file_are_caught(session: AsyncSession) -> None:
    csv = (
        b"booking_date,amount,description,external_id\n"
        b"2026-09-18,612.40,HOTEL,TX-1\n"
        b"2026-09-18,612.40,HOTEL,TX-1\n"
    )

    result = await BankService(session).import_csv(csv)

    assert result.inserted == 1
    assert result.skipped_duplicates == 1


async def test_rows_without_external_id_are_all_kept(session: AsyncSession) -> None:
    """Rows without external_id cannot be deduped — both identical coffees stay"""
    csv = (
        b"booking_date,amount,description\n"
        b"2026-09-18,3.50,COFFEE\n"
        b"2026-09-18,3.50,COFFEE\n"
    )

    result = await BankService(session).import_csv(csv)

    assert result.inserted == 2
    assert result.skipped_duplicates == 0


async def test_empty_file_reports_a_readable_error(session: AsyncSession) -> None:
    result = await BankService(session).import_csv(b"")

    assert result.inserted == 0
    assert result.errors[0].reason == "The file has no header"


def test_header_normalization() -> None:
    assert normalize_header(" Booking Date ") == "booking_date"
    assert normalize_header("\ufeffdate") == "booking_date"
    assert normalize_header("Unknown Column") == "unknown_column"
