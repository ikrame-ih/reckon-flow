# Phase 1 — Ledger

## Goal

Money that cannot lie: Decimal everywhere, balanced double-entry, append-only
history.

## Worked example

```http
POST /api/v1/accounts
{"code":"CASH","name":"Cash","currency":"EUR"}

POST /api/v1/ledger/transactions
{
  "reference": "TX-1",
  "description": "Hotel from cash",
  "lines": [
    {"account_id": 2, "debit": "120.00", "credit": "0", "currency": "EUR"},
    {"account_id": 1, "debit": "0", "credit": "120.00", "currency": "EUR"}
  ]
}
```

Amounts are **strings**. Sending `120.00` as a JSON number is rejected —
floats already lost precision before they reach the ledger.

## Failure case

An unbalanced body returns **422** and leaves **zero** rows:

```json
{"error": "UnbalancedLedgerError", "detail": "Unbalanced transaction: debit=100 credit=50"}
```

Postgres also has a deferred trigger so a buggy script cannot commit an
unbalanced set even if it bypasses the service. Balances leave the API as
`MoneyStr` (JSON strings) so clients never round float money.

Paths: `core/money.py`, `services/ledger.py`, `alembic/versions/001_*.py`
