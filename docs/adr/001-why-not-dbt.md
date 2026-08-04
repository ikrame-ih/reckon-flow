# ADR 001: Why not dbt

- **Status:** Accepted
- **Date:** 2026-08-03
- **Phase:** 0

## Context

When I sketched ReckonFlow I assumed dbt would sit in the middle: bank
CSVs and invoice payloads land in a raw zone, dbt models clean and join
them, and the API reads from a reconciliation mart.

That picture fits a warehouse. ReckonFlow is not one. A trip approval,
a ledger post, and a bank match have to happen on the request path, with
row locks and idempotent retries. Waiting on a batch transform (or
pretending dbt is my validation layer) fights that shape.

## Decision

I dropped dbt from the stack.

CSV rows and API bodies are validated with Pydantic as they arrive.
Alembic owns the schema. Matching and money rules stay in the service
layer next to the endpoints that call them.

If I ever need analyst-facing marts on top of exported ledger data, dbt
can come back for that layer alone — not for the live API.

## Consequences

Fewer moving parts in CI and local setup. Domain rules live in one place
instead of being split between Python and SQL models. Adding reporting
later does not require rewriting the ledger.
