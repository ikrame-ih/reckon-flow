# ReckonFlow

Headless FastAPI backend for corporate travel approvals, an immutable
double-entry ledger, structured receipt extraction, and hybrid bank
reconciliation.

> **Status: Phases 0–6 implemented**
> Live demo (when deployed): `https://YOUR-SERVICE.onrender.com/docs`
> Unit tests run offline (SQLite). Production stack: Neon + Render + Upstash Redis.

## Why this project

Admin teams often juggle three disconnected flows:

1. Travel pre-requests waiting for approval
2. Bookings made outside the approval system
3. Manual reconciliation of bank CSVs against receipts

ReckonFlow unifies those flows behind an API so finance reviews exceptions
instead of matching every line by hand.

## Architecture

```mermaid
flowchart TD
  Client[API Client] --> MW[Idempotency Middleware]
  MW -->|"SET NX EX 86400"| Redis[(Redis)]
  MW --> Routers[FastAPI Routers]
  Routers --> Services[Service Layer]
  Services --> PG[("PostgreSQL + pgvector<br/>Double-entry Ledger")]
  Routers -->|"202 Accepted"| BG[Background Tasks]
  BG --> LLM[Groq free tier / stub]
  LLM -->|Structured receipt data| Services
  Services --> Recon[Reconciliation Engine<br/>SQL + RapidFuzz + RRF]
  Recon --> PG
```

## Stack

| Layer | Choice |
| --- | --- |
| API | Python 3.12 + FastAPI |
| DB | PostgreSQL + pgvector (SQLite in unit tests) |
| Cache | Redis (`Idempotency-Key`, cached responses) |
| ORM | SQLAlchemy 2 async + Alembic |
| Extraction | Groq free tier via a thin provider interface (stub when no key) |
| Matching | Date/amount prefilter + RapidFuzz + optional embeddings + RRF (k=60) |
| Tooling | uv, Ruff, mypy, pytest, Docker Compose, GitHub Actions |

## Quick start (Windows without Docker)

Docker needs WSL2. If WSL is broken, use **native PostgreSQL** instead:

1. Install PostgreSQL 16 (winget: `winget install PostgreSQL.PostgreSQL.16`)
2. Create DB: `psql -U postgres -c "CREATE DATABASE reckonflow;"`
3. Copy `.env.example` → `.env` and set:
   `DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/reckonflow`
   `IDEMPOTENCY_ENABLED=false` (Redis optional; middleware fails open anyway)
4. Then:

```bash
uv sync
uv run alembic upgrade head
uv run python scripts/seed_demo.py
uv run uvicorn reckonflow.main:app --reload --port 8000
```

## Quick start (Docker, when WSL works)

```bash
uv sync
docker compose up -d
uv run alembic upgrade head
uv run python scripts/seed_demo.py
uv run uvicorn reckonflow.main:app --reload --port 8000
```

Interactive docs: http://localhost:8000/docs

## Deploy (recruiter link)

Stack I use for a public demo:

| Piece | Service |
| --- | --- |
| API | Render (free web service) |
| Database | Neon Postgres |
| Idempotency | Upstash Redis |
| Migrations | `scripts/render_start.sh` runs `alembic upgrade head` on boot |

After deploy, put this in the README header:

`Live demo: https://<your-app>.onrender.com/docs`

Seed once from the Render shell: `uv run python scripts/seed_demo.py`

## Quality checks

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest
uv run python scripts/run_evals.py
```

## Build plan

| Phase | Focus | Status |
| --- | --- | --- |
| 0 | Skeleton, `/health`, tooling, CI | Done |
| 1 | Double-entry ledger | Done |
| 2 | Travel requests + approvals + bank CSV | Done |
| 3 | Redis idempotency | Done |
| 4 | Receipt extraction + evals + untrusted-input ADR | Done |
| 5 | Hybrid reconciliation + `FOR UPDATE` | Done |
| 6 | OpenAPI polish, seed, README | Done |

## Decisions

See [`docs/adr/`](docs/adr/):

- [001 Why not dbt](docs/adr/001-why-not-dbt.md)
- [002 Receipt content is untrusted](docs/adr/002-receipt-untrusted-input.md)
- [003 Redis idempotency](docs/adr/003-redis-idempotency.md)
