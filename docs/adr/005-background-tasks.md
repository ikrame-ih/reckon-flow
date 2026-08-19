# ADR 005: BackgroundTasks now, durable queue later

- **Status:** Superseded by [ADR 007](007-durable-receipt-jobs.md)
- **Date:** 2026-08-04
- **Phase:** 4 / 6

## Context

Receipt extraction can take seconds. Blocking the upload response on the model
call hurts UX and ties up workers.

## Decision

Use FastAPI `BackgroundTasks` after returning **202 Accepted**. The task opens
its own DB session because the request session is closed before the task runs.

This is **not** a durable queue: process crash loses in-flight work. The
upgrade path is adding **arq** (async Redis jobs) or Celery later without
changing the HTTP contract — callers already poll `GET /receipts/{id}`.
No worker package ships in-tree until that path is wired end-to-end.

## Consequences

- Simple deploy (one process) for the demo
- No retries / DLQ yet — failed extractions stay `failed` for a manual re-run
- Idempotency middleware must preserve `response.background` when caching
