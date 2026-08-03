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

Optional: set `API_KEY` in `.env` and send `X-API-Key` on POST/PUT/PATCH/DELETE.

## Demo order

1. `GET /api/v1/accounts` — chart of accounts (after seed: CASH, TRAVEL)
2. `POST /api/v1/travel-requests` — creates a pending approval
3. `POST /api/v1/approvals/{id}/transition` with `{"action":"approve"}`
4. `POST /api/v1/expenses` — amounts as **strings**; link to the approved trip
5. `POST /api/v1/bank/import` — multipart CSV
6. `POST /api/v1/reconciliation/expenses/{id}/suggest`
7. `POST /api/v1/receipts?expense_id=` — returns **202**; poll `GET /receipts/{id}`

Always send money as JSON strings (`"120.50"`), never as numbers.

## Deploy shape

| Piece | Host |
| --- | --- |
| API | Render |
| Database | Neon |
| Idempotency | Upstash Redis |

### Production checklist (Render env)

After each deploy, `GET /health` should show `"status":"ok"` with both
`database` and `redis` true. If `redis` is false, idempotency is fail-open.

1. `DATABASE_URL` — Neon URL with `postgresql+asyncpg://` and `ssl=require`
2. `REDIS_URL` — Upstash **`rediss://`** URL (TLS). Rotate the token if it
   was ever pasted into chat, then paste the new value into Render.
3. `API_KEY` — non-empty; mutating routes return 401 without `X-API-Key`
4. Confirm start logs include `alembic upgrade head` reaching revision `002`

Details: [Phase 6](phases/06-polish.md). Docs site: https://ikrame-ih.github.io/reckon-flow/
