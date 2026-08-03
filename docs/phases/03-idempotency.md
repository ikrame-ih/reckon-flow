# Phase 3 — Idempotency

## Goal

A timed-out POST that the client retries must not double-post money.

## Worked example

```http
POST /api/v1/expenses
Idempotency-Key: 9f3c-ada-hotel
{"vendor":"Hotel Mitte","description":"...","amount":"120.00",...}

# Client times out, retries the exact same body + key:
POST /api/v1/expenses
Idempotency-Key: 9f3c-ada-hotel
...
→ same JSON body, header Idempotency-Replayed: true, handler ran once
```

Redis claim: `SET key NX EX 86400` — write only if the key does not exist,
expire after 24h. See the [glossary](../glossary.md#set-nx-ex-86400).

## Failure case

While the first request is still running, a retry gets **409**
`IdempotencyConflict`. If Redis is down, the middleware **fails open**
(request proceeds, retry protection is lost) — documented in
[ADR 003](../adr/003-redis-idempotency.md).

## What went wrong once

Rebuilding the cached response dropped FastAPI `BackgroundTasks`, so receipt
extraction never ran when a key was sent. The rebuild now copies `background`
across.

**Key paths:** `api/middleware/idempotency.py`, ADR 003
