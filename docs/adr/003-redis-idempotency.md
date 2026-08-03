# ADR 003: Redis idempotency with cached responses

- **Status:** Accepted
- **Date:** 2026-08-03
- **Phase:** 3

## Context

Clients retry POSTs on timeouts. Without protection, retries can double-post
ledger entries or bank imports.

## Decision

Use an `Idempotency-Key` header with Redis:

1. `SET key NX EX 86400` claims the key for 24 hours
2. On first success, store status code + body
3. A duplicate key returns the **original cached response** (not only 409)
4. Replays are marked with `Idempotency-Replayed: true`

## Accepted risk: fail-open

When Redis is unreachable, the middleware logs a warning and lets the request
through. Availability wins over retry protection for that moment. Redis is
therefore **not** a hard dependency for serving traffic — only for the
idempotency guarantee. Prefer fixing Redis over flipping this to fail-closed
for a public demo API.

## Consequences

- Safe retries for mutating endpoints when Redis is healthy
- Tests inject a fake Redis client so CI stays offline
- Operators should monitor `idempotency.redis_unavailable` warnings
