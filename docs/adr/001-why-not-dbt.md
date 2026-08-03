# ADR 001: Why not dbt

- **Status:** Accepted
- **Date:** 2026-08-03
- **Phase:** 0

## Context

ReckonFlow is a transactional API (OLTP): it records travel approvals,
ledger entries, receipt extractions, and bank matches in near real time
Some portfolio plans and industry write-ups recommend dbt for data
transformations — that advice fits analytics warehouses, not this API

## Decision

I do **not** use dbt in ReckonFlow

I keep row validation and shaping in the application layer:

- Pydantic models validate CSV bank rows and API payloads
- SQLAlchemy + Alembic own the schema and migrations
- Business rules live in the service layer

I leave dbt as a **future option** only if I later add a reporting /
analytics layer (OLAP) on top of exported ledger data

## Consequences

- One less tool in the stack — faster onboarding and CI
- Transformations stay close to the domain code recruiters will read
- If I need marts later, I can introduce dbt without rewriting the ledger
