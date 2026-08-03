# Getting started

## Live demo

Open **[https://reckon-flow.onrender.com/docs](https://reckon-flow.onrender.com/docs)**.

Free Render instances sleep when idle — the first request may take up to a minute.

Try, in order:

1. `GET /health`
2. `GET /api/v1/accounts` (seeded `CASH` / `TRAVEL`)
3. `POST /api/v1/ledger/transactions` with amounts as **strings**
4. Optional: upload a receipt under **receipts**, then poll `GET /api/v1/receipts/{id}`

## Run locally

```bash
uv sync
cp .env.example .env   # set DATABASE_URL to your Postgres
uv run alembic upgrade head
uv run python scripts/seed_demo.py
uv run uvicorn reckonflow.main:app --reload --port 8000
```

Quality checks:

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest
uv run python scripts/run_evals.py
```

## Deploy shape

| Piece | Host |
| --- | --- |
| API | Render |
| Postgres | Neon |
| Redis (idempotency) | Upstash (can share one DB; keys use prefix `reckonflow:`) |

See [phase 6](phases/06-polish.md) for more detail.
