# ADR 006: Redis-backed rate limiting with memory fallback

- **Status:** Accepted
- **Date:** 2026-08-04
- **Phase:** post-0–6 polish

## Context

Rate limiting lived in-process (`deque` per key). That works on a single
Render free instance and fails as soon as there are two workers: each process
has its own counter, so the effective limit doubles.

## Decision

Use Redis `INCR` + `EXPIRE` (60s fixed window) keyed by `X-API-Key` or client
host, namespaced with `redis_key_prefix`.

When Redis is unreachable, fall back to the in-memory window. Unlike
idempotency (ADR 003), we do **not** fail fully open: a cache outage must not
remove all request caps on a public demo.

## Consequences

- Shared limits across instances when Redis is healthy
- Tests inject a fake Redis the same way as idempotency tests
- Operators should watch `rate_limit.redis_unavailable` warnings
