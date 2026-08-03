"""I seed demo data so anyone can try the API without inventing rows by hand

Run after Postgres is up:
  docker compose up -d
  uv run alembic upgrade head   # or let create_all below cover local demos
  uv run python scripts/seed_demo.py
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

from reckonflow.core.db import SessionLocal, engine
from reckonflow.models import Base
from reckonflow.models.travel import ApprovalStatus
from reckonflow.services.bank import BankService
from reckonflow.services.ledger import LedgerService
from reckonflow.services.travel import TravelService


async def seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        ledger = LedgerService(session)
        travel = TravelService(session)
        bank = BankService(session)

        cash = await ledger.create_account(
            code="CASH", name="Cash on hand", currency="EUR"
        )
        travel_acct = await ledger.create_account(
            code="TRAVEL", name="Travel expenses", currency="EUR"
        )

        await ledger.create_balanced_transaction(
            reference="SEED-001",
            description="Seed: pay hotel from cash",
            lines=[
                {
                    "account_id": travel_acct.id,
                    "debit": "120.00",
                    "credit": "0",
                    "currency": "EUR",
                },
                {
                    "account_id": cash.id,
                    "debit": "0",
                    "credit": "120.00",
                    "currency": "EUR",
                },
            ],
        )

        trip = await travel.create_travel_request(
            employee_name="Ada Lovelace",
            destination="Berlin",
            purpose="Conference",
            start_date=date.today() - timedelta(days=10),
            end_date=date.today() - timedelta(days=7),
            estimated_amount=Decimal("500.00"),
            currency="EUR",
        )
        assert trip.approval is not None
        await travel.transition_approval(
            trip.approval.id,
            target=ApprovalStatus.APPROVED,
            reviewer="Finance Bot",
            notes="Seed approval",
        )

        await travel.create_expense(
            travel_request_id=trip.id,
            vendor="Hotel Mitte",
            description="Hotel Mitte Berlin 3 nights",
            amount=Decimal("120.00"),
            currency="EUR",
            expense_date=date.today() - timedelta(days=8),
        )

        csv_body = (
            "booking_date,amount,currency,description,external_id\n"
            f"{(date.today() - timedelta(days=8)).isoformat()},"
            "-120.00,EUR,CARD HOTEL MITTE BERLIN,SEED-BANK-1\n"
            f"{(date.today() - timedelta(days=3)).isoformat()},"
            "-45.50,EUR,TAXI BERLIN CENTRE,SEED-BANK-2\n"
        ).encode()
        result = await bank.import_csv(csv_body)
        await session.commit()
        print(
            "Seed complete:",
            f"accounts=2 ledger_tx=1 trip=1 expense=1 bank_inserted={result.inserted}",
        )


if __name__ == "__main__":
    asyncio.run(seed())
