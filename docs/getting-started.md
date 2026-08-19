# Getting started

## Local

```bash
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run python scripts/seed_demo.py
uv run uvicorn reckonflow.main:app --reload --port 8000
```

Open http://localhost:8000/docs

Optional: set `API_KEY` in `.env` and send `X-API-Key` on **all** finance
`/api/v1` calls (reads and writes). `/health`, `/ready`, and docs stay public.

## Demo order

1. `GET /api/v1/accounts` — chart of accounts (after seed: CASH, TRAVEL)
2. `POST /api/v1/travel-requests` — creates a pending approval
3. `POST /api/v1/approvals/{id}/transition` with `{"action":"approve"}`
4. `POST /api/v1/expenses` — amounts as **strings**; link to the approved trip
5. `POST /api/v1/bank/transactions/upload` — multipart CSV
6. `GET /api/v1/reconciliation/expenses/{id}/suggestions`
7. `POST /api/v1/receipts` — multipart form: `file` + optional `expense_id`;
   returns **202**; poll `GET /api/v1/receipts/{id}`

Always send money as JSON strings (`"120.50"`), never as numbers.

## Deploy shape

| Piece | Host |
| --- | --- |
| API | Render |
| Database | Neon |
| Idempotency | Upstash Redis |

### Production checklist (Render env)

After each deploy, `GET /ready` should return HTTP 200 with `"database": true`.
`GET /health` is liveness (always 200 while the process is up). If `redis` is
false on either probe, idempotency is fail-open.

1. `DATABASE_URL` — Neon URL with `postgresql+asyncpg://` and `ssl=require`
2. `REDIS_URL` — Upstash **`rediss://`** URL (TLS). Rotate the token if it
   was ever exposed, then paste the new value into Render.
3. `API_KEY` — **required**; production refuses to boot if empty
4. Confirm start logs include `alembic upgrade head` reaching revision `005`

Details: [Phase 6](phases/06-polish.md). Docs site: https://ikrame-ih.github.io/reckon-flow/
