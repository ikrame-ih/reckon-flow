# ADR 001: Why not dbt

- **Status:** Accepted
- **Date:** 2026-08-03
- **Phase:** 0

## Context

ReckonFlow is a transactional API (OLTP): it records travel approvals,
ledger entries, receipt extractions, and bank matches in near real time.
dbt fits analytics warehouses (OLAP), not request-path validation for an API.

## Decision

Do **not** use dbt in ReckonFlow.

Keep row validation and shaping in the application layer:

- Pydantic models validate CSV bank rows and API payloads
- SQLAlchemy + Alembic own the schema and migrations
- Business rules live in the service layer

Leave dbt as a **future option** only if a reporting / analytics layer is
added on top of exported ledger data.

## Consequences

- One less tool in the stack — faster onboarding and CI
- Transformations stay in the service layer next to the domain rules they enforce
- Marts can be introduced later without rewriting the ledger
