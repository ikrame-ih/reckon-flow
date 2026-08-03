# Phase 6 — Polish and deploy

## Goal

Runnable demo: seed data, OpenAPI, Render + Neon + Upstash, docs site, auth
story.

## Deploy shape

| Piece | Host |
| --- | --- |
| API | Render (`scripts/render_start.sh` runs migrations then uvicorn) |
| Database | Neon Postgres |
| Idempotency | Upstash Redis (`REDIS_KEY_PREFIX=reckonflow:`) |
| Docs | MkDocs → GitHub Pages |

Set `API_KEY` on Render so mutating routes require `X-API-Key`. Leave it empty
only for local exploration.

## Demo path (after seed)

1. Open [Swagger](https://reckon-flow.onrender.com/docs)
2. `GET /api/v1/accounts` — CASH and TRAVEL
3. `GET /api/v1/expenses` then `POST /api/v1/reconciliation/expenses/{id}/suggest`

Free Render sleeps when idle — first request can take ~50s.

## What went wrong once

Neon URLs include `channel_binding=require`, which asyncpg rejects. The URL
rewriter in `core/config.py` strips it and maps `sslmode` → `ssl=require`.

**Key paths:** `scripts/seed_demo.py`, `scripts/render_start.sh`, ADR 004
