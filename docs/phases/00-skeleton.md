# Phase 0 — Skeleton

## Goal

A cloneable Python package with health checks, settings, logging, and CI —
not a pile of scripts.

## What landed

- `uv` project with `src/reckonflow` layout
- FastAPI app factory + `GET /health`
- Settings via pydantic-settings (`.env` + environment variables)
- Structured logging with structlog
- Ruff, mypy, pytest, GitHub Actions CI

## How it fits together

`create_app()` builds the FastAPI instance so tests can construct a fresh app
without starting uvicorn. Settings load once per process (`get_settings`).
Logs use console formatting in debug and JSON otherwise.

```bash
uv run uvicorn reckonflow.main:app --reload --port 8000
curl http://localhost:8000/health
# {"status":"ok","app":"ReckonFlow","version":"0.1.0"}
```

Early on I mixed a module-level `app = FastAPI()` with test overrides. A factory
made Redis and middleware injection straightforward. See `main.py`,
`core/config.py`, and `core/logging.py`.
