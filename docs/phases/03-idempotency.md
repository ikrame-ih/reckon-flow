# Phase 3 — Idempotency

## What was built

- Middleware that reads `Idempotency-Key` on mutating methods
- Redis `SET key NX EX 86400` to claim the key for 24 hours
- Cached status + body replay on duplicates (`Idempotency-Replayed: true`)
- Key prefix (`reckonflow:`) so one Upstash free database can be shared
- Fail-open behaviour if Redis is unreachable

## Why

Clients retry when the network drops after the server already committed. Without
idempotency, a second `POST` can double-create expenses or ledger rows.

## How it works

See the glossary entry for **SET NX EX 86400**. The middleware hashes the body
so the same key cannot be reused for a different payload silently. ADR:
[003](../adr/003-redis-idempotency.md).

**Key paths:** `api/middleware/idempotency.py`, `core/redis.py`
