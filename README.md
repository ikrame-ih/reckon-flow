# ReckonFlow

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-Upstash-DC382D?logo=redis&logoColor=white)
![Ruff](https://img.shields.io/badge/Ruff-lint-D7FF64?logo=ruff&logoColor=black)

**Headless FastAPI backend for corporate travel** — approvals, an immutable
double-entry ledger, LLM receipt extraction, and hybrid bank reconciliation.

Built to force the hard parts of finance software (money precision, retries,
concurrency, untrusted model output) instead of another CRUD demo.

| | |
| --- | --- |
| **Live API** | [reckon-flow.onrender.com/docs](https://reckon-flow.onrender.com/docs) (Scalar) |
| **Documentation** | [GitHub Pages](https://ikrame-ih.github.io/reckon-flow/) |
| **Source** | [github.com/ikrame-ih/reckon-flow](https://github.com/ikrame-ih/reckon-flow) |

> Free Render instances sleep when idle — the first request can take ~50s.

## The problem

Travel finance breaks in boring ways: a retried POST double-pays an expense, a
float rounds a ledger out of balance, two reviewers claim the same bank line,
or receipt text tries to talk the model into approving spend.

ReckonFlow explores that domain as a **headless API**: clear money rules,
idempotent writes, row locks on reconcile, and schema-bound extraction so the
LLM cannot take actions — only fill structured fields.

## What you get

| Area | Role |
| --- | --- |
| **Travel + approvals** | Trip request → `pending` / `approved` / `paid` / `rejected` |
| **Ledger** | Append-only double-entry; money as JSON strings (`MoneyStr`) |
| **Receipts** | Upload → **202** + background extract (Groq or offline stub) |
| **Bank import** | CSV ingest with `external_id` dedup |
| **Reconciliation** | SQL prefilter → RapidFuzz → embeddings → RRF (`k=60`) |
| **Ops** | `Idempotency-Key`, `X-API-Key` on writes, request IDs, `/metrics`, deep `/health` |

Interactive docs: **Scalar** at `/docs` · classic Swagger at `/swagger` · ReDoc at `/redoc`.

## 60-second demo path

Open the [live API docs](https://reckon-flow.onrender.com/docs) (after seed, or
run the quick start locally):

1. `GET /api/v1/accounts` → `CASH`, `TRAVEL`
2. `GET /api/v1/expenses` → note an expense `id`
3. `GET /api/v1/reconciliation/expenses/{id}/suggestions` → ranked bank candidates
4. Optional: create a trip → approve → add expense → upload bank CSV → confirm match

Mutating calls on production need `X-API-Key` when that env var is set.

## Architecture (short)

```
Client
  → Idempotency middleware (Redis SET NX EX)
  → FastAPI routers
  → Services (travel, ledger, bank, receipts, reconciliation)
  → PostgreSQL

Receipt upload → 202 → BackgroundTasks → Groq / stub → structured JSON
```

Interesting decisions (detail in docs / ADRs):

- **Money as strings** across the wire — JSON numbers become floats in most clients.
- **RRF over weighted averages** — RapidFuzz and cosine are not on one scale.
- **Schema containment** (`extra="forbid"`) for receipt extraction — not prompt trust.
- **Fail-open idempotency** when Redis is down — availability over strict retries (ADR 003).

## Trade-offs and limitations

- Auth is a **shared API key** on mutating routes — no roles, tenants, or ownership yet (ADR 004).
- Receipt work uses FastAPI **BackgroundTasks**, not a durable queue (ADR 005).
- Rate limiting is **in-process**; multi-instance needs a shared store.
- Embeddings are a **deterministic stand-in** offline; optional real vectors later.
- Demo storage for receipts is local disk (ephemeral on free PaaS).

## Quick start

**Prerequisites:** Python 3.12+, [uv](https://github.com/astral-sh/uv), PostgreSQL
(or Neon), Redis optional for idempotency.

```bash
git clone https://github.com/ikrame-ih/reckon-flow.git
cd reckon-flow
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run python scripts/seed_demo.py
uv run uvicorn reckonflow.main:app --reload --port 8000
```

Open [http://localhost:8000/docs](http://localhost:8000/docs).

## Scripts

| Command | Purpose |
| --- | --- |
| `uv run uvicorn reckonflow.main:app --reload` | API server |
| `uv run alembic upgrade head` | Apply migrations |
| `uv run python scripts/seed_demo.py` | Demo chart + sample data |
| `uv run ruff check src tests` | Lint |
| `uv run ruff format --check src tests` | Format check |
| `uv run mypy src` | Strict types |
| `uv run pytest --cov=reckonflow` | Tests (+ coverage) |
| `uv run pip-audit` | Dependency CVEs |
| `uv run python scripts/run_evals.py` | Receipt stub evals |
| `uv run mkdocs serve` | Docs site locally |

**CI (every push/PR):** ruff · format · mypy · Alembic against Postgres ·
pytest + coverage floor · pip-audit · evals · MkDocs strict build. Docs deploy
to GitHub Pages on push to `main`.

## Stack

Python 3.12 · FastAPI · SQLAlchemy 2 async · Alembic · PostgreSQL / Neon ·
Redis / Upstash · RapidFuzz · Groq / PydanticAI · Ruff · mypy · pytest ·
MkDocs Material · Render

## Environment

Copy `.env.example` → `.env`. Never commit secrets.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Postgres (`postgresql+asyncpg://…`) |
| `REDIS_URL` | Upstash / Redis (`rediss://…` for TLS) |
| `API_KEY` | Gate mutating routes + `/metrics` (empty = open, local/CI) |
| `GROQ_API_KEY` | Receipt LLM; empty → deterministic stub |
| `REDIS_KEY_PREFIX` | Namespace when sharing a Redis DB |
| `RATE_LIMIT_PER_MINUTE` | In-process sliding window |
| `METRICS_ENABLED` | Prometheus `/metrics` |

## Project layout

```
src/reckonflow/
  api/          # Routers, middleware, deps
  services/     # Business rules
  models/       # SQLAlchemy tables
  schemas/      # Pydantic I/O
  ai/           # Groq + stub extractors
  core/         # Config, DB, money, redis, embeddings
  tasks/        # BackgroundTasks helpers
alembic/        # Migrations
docs/           # MkDocs (phases, glossary, ADRs, security)
evals/          # Receipt fixtures
tests/
scripts/        # seed_demo, run_evals, render_start
```

## Possible next steps

If this grew past a portfolio API: OIDC + roles, a durable job queue (arq/Celery)
for receipts, Redis-backed rate limits, and real embedding providers behind the
same reconciliation interface.

## Documentation

- [Getting started](https://ikrame-ih.github.io/reckon-flow/getting-started/)
- [Build phases](https://ikrame-ih.github.io/reckon-flow/phases/) — ledger → travel → recon
- [Glossary](https://ikrame-ih.github.io/reckon-flow/glossary/) — `SET NX EX`, RRF, `MoneyStr`…
- [Security](https://ikrame-ih.github.io/reckon-flow/security/)
- [ADRs](https://ikrame-ih.github.io/reckon-flow/adr/) — auth scope, fail-open, background tasks

## Author

**Ikrame Ibn Hayoun** — [Portfolio](https://ikrame.dev/) · [GitHub](https://github.com/ikrame-ih) · [LinkedIn](https://www.linkedin.com/in/ikrame-ih/)

Vulnerability reports: [SECURITY.md](./SECURITY.md). Contributing notes: [CONTRIBUTING.md](./CONTRIBUTING.md).
