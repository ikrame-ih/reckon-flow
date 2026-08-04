# ReckonFlow

Headless FastAPI backend for corporate travel approvals, an immutable
double-entry ledger, structured receipt extraction, and hybrid bank
reconciliation.

**Live API:** [Swagger on Render](https://reckon-flow.onrender.com/docs)  
**Docs:** [GitHub Pages](https://ikrame-ih.github.io/reckon-flow/)

> Free Render instances sleep when idle — the first request can take ~50s.

## Why I built this

I wanted a backend project that forces the hard parts of finance software —
money precision, retries, concurrency, and untrusted LLM output — instead of
another CRUD todo API. Corporate travel is a concrete domain where those
failures show up as duplicate reimbursements and silent mismatches.

## Lessons learned

- Floats in JSON are a footgun; money must cross the wire as strings.
- Idempotency is a protocol (key + body hash + cached response), not a unique
  constraint alone.
- RapidFuzz scores and embedding cosine are not on the same scale — RRF ranks
  beat weighted averages.
- Schema containment beats prompt instructions when the model sees hostile text.

## 30-second demo

After [seed](#quick-start) (or on the live [Swagger demo](https://reckon-flow.onrender.com/docs) once seeded):

1. `GET /api/v1/accounts` → `CASH`, `TRAVEL`
2. `GET /api/v1/expenses` → note an expense `id`
3. `GET /api/v1/reconciliation/expenses/{id}/suggestions` → ranked bank candidates

Mutating calls on production should send `X-API-Key` when that env var is set.
Architecture and walkthroughs live on the
[docs site](https://ikrame-ih.github.io/reckon-flow/).

## Stack

| Layer | Choice |
| --- | --- |
| API | Python 3.12 + FastAPI |
| DB | PostgreSQL / Neon (SQLite in unit tests) |
| Cache | Redis / Upstash (`Idempotency-Key`) |
| ORM | SQLAlchemy 2 async + Alembic |
| Extraction | Groq when `GROQ_API_KEY` is set; stub otherwise |
| Matching | Date/amount/currency prefilter + RapidFuzz + embeddings + RRF (k=60) |
| Docs | MkDocs Material → GitHub Pages |
| Ops | Request IDs, `/metrics`, rate limit, API key on writes |

## Quick start

```bash
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run python scripts/seed_demo.py
uv run uvicorn reckonflow.main:app --reload --port 8000
```

Local docs: http://localhost:8000/docs · Metrics: http://localhost:8000/metrics

## Quality checks

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest --cov=reckonflow
uv run pip-audit
uv run python scripts/run_evals.py
```

## Build plan

| Phase | Focus | Status |
| --- | --- | --- |
| 0–6 | Skeleton → ledger → travel → idempotency → receipts → recon → deploy | Done |

Walkthrough: [Build phases](https://ikrame-ih.github.io/reckon-flow/phases/) or `docs/phases/`.

## Decisions

- [001 Why not dbt](docs/adr/001-why-not-dbt.md)
- [002 Receipt content is untrusted](docs/adr/002-receipt-untrusted-input.md)
- [003 Redis idempotency](docs/adr/003-redis-idempotency.md)
- [004 API-key auth](docs/adr/004-api-key-auth.md)
- [005 Background tasks vs queue](docs/adr/005-background-tasks.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
