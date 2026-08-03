# ADR 003: Redis idempotency with cached responses

- **Status:** Accepted
- **Date:** 2026-08-03
- **Phase:** 3

## Context

Clients retry POSTs on timeouts. Without protection, retries can double-post
ledger entries or bank imports

## Decision

I use an `Idempotency-Key` header with Redis:

1. `SET key NX EX 86400` claims the key for 24 hours
2. On first success I store status code + body
3. A duplicate key returns the **original cached response** (not only 409)
4. Replays are marked with `Idempotency-Replayed: true`

## Consequences

- Safe retries for mutating endpoints
- Redis becomes a hard dependency when idempotency is enabled
- Tests inject a fake Redis client so CI stays offline
