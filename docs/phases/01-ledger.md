# Phase 1 — Double-entry ledger

## What was built

- `Account`, `LedgerTransaction`, `LedgerEntry` models
- Amounts as `NUMERIC(15, 4)` plus ISO `currency`
- `parse_money` / `MoneyStr` — no floats on the wire
- Service that rejects unbalanced writes
- Alembic migration with one-sided entry checks and a deferred balance trigger on Postgres
- REST endpoints for accounts and transactions

## Why

A single mutable `balance` column loses history and races under concurrency.
Double-entry treats money as events: every transaction has debits and credits
that cancel out. Append-only rows keep an audit trail.

## How it works

Balances are computed with `SUM(debit) - SUM(credit)`, never stored as a
writable field. Corrections are new reversing transactions, not `UPDATE`s on
old lines. JSON responses serialize money as strings so JavaScript clients do
not turn amounts into IEEE floats.

**Key paths:** `models/ledger.py`, `services/ledger.py`, `schemas/ledger.py`,
`core/money.py`, `alembic/versions/001_initial_schema.py`

See also ADR-style notes in the glossary under **double-entry** and **MoneyStr**.
