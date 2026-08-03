# ADR 005: BackgroundTasks now, durable queue later

- **Status:** Accepted
- **Date:** 2026-08-04
- **Phase:** 4 / 6

## Context

Receipt extraction can take seconds. Blocking the upload response on the model
call hurts UX and ties up workers.

## Decision

Use FastAPI `BackgroundTasks` after returning **202 Accepted**. The task opens
its own DB session because the request session is closed before the task runs.

This is **not** a durable queue: process crash loses in-flight work. The
upgrade path is **arq** (async Redis jobs) or Celery without changing the
HTTP contract — callers already poll `GET /receipts/{id}`.

## Consequences

- Simple deploy (one process) for the demo
- No retries / DLQ yet — failed extractions stay `failed` for a manual re-run
- Idempotency middleware must preserve `response.background` when caching
