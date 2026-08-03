# Phase 2 — Travel business flow

## What was built

- `TravelRequest`, `Approval`, `Expense`, `Receipt`, `BankTransaction`
- Creating a trip also creates a pending approval
- State machine: pending → approved|rejected; approved → paid
- Bank CSV import with per-row Pydantic validation and bulk insert

## Why

Travel spend is the product story: request → approve → spend → match to the
bank. CSV validation in the app replaces any need for a separate transform
tool (dbt) at ingest time — see [ADR 001](../adr/001-why-not-dbt.md).

## How it works

Illegal status jumps raise a domain error before the database changes.
Bank headers are normalized through aliases (`booking date` → `booking_date`).
Duplicate `external_id`s are skipped so re-uploading yesterday's file is safe.

**Key paths:** `models/travel.py`, `services/travel.py`, `services/bank.py`,
`api/v1/travel.py`, `api/v1/approvals.py`, `api/v1/bank.py`
