# Phase 0 — Skeleton

## What was built

- `uv` project with `src/reckonflow` layout
- FastAPI app factory + `GET /health`
- Settings via pydantic-settings (`.env` + environment variables)
- Structured logging with structlog
- Ruff, mypy, pytest, GitHub Actions CI
- Docker Compose file for Postgres/Redis (optional; native Postgres also works)

## Why

A recruiter should clone (or open the live demo) and see a real Python package,
not a pile of scripts. Health checks and CI signal that the project is meant to
stay runnable.

## How it works

`create_app()` builds the FastAPI instance so tests can construct a fresh app
without starting uvicorn. Settings load once per process (`get_settings`).
Logs use console formatting in debug and JSON in production-style runs.

**Key paths:** `src/reckonflow/main.py`, `core/config.py`, `core/logging.py`,
`.github/workflows/ci.yml`
