# ADR 007: Durable receipt jobs with ARQ

- **Status:** Accepted
- **Date:** 2026-08-19
- **Phase:** P1
- **Supersedes:** [ADR 005](005-background-tasks.md) for production/demo with Redis

## Context

ADR 005 used FastAPI `BackgroundTasks` after **202**. A process crash lost
in-flight extraction. Recruiters and the 90-day plan need a queue with retry
and a stable job id.

Render free is still **one** web instance. A second paid worker is nicer; until
then the API start script can run `arq` in the same service.

## Decision

- Queue name `REDIS_KEY_PREFIX` + `:arq` (default `reckonflow:arq`).
- Job function `extract_receipt(receipt_id)` with `_job_id=receipt-extract:{id}`.
- `max_tries=3`. The job **raises** after recording a failed `extraction_runs`
  row so ARQ retries. Already-`extracted` rows no-op.
- `RECEIPT_QUEUE=inline` in tests: keep BackgroundTasks so pytest needs no
  Redis worker.
- `RECEIPT_QUEUE=arq` when Redis is up (local compose, Render). If enqueue
  fails, fall back to inline and log `receipt.arq_enqueue_failed` — the demo
  still extracts; that path is **not** durable.

HTTP contract unchanged: **202** + poll `GET /receipts/{id}`.

## Consequences

- Need Redis **and** a running ARQ process for durability.
- Tracing is a table + `GET /api/v1/receipts/runs`, not Langfuse.
- Token counts stay `null` until a provider exposes usage (stub never will).
