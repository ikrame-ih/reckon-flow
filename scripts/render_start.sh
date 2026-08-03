#!/usr/bin/env bash
# I start ReckonFlow on Render after applying migrations
# Seed is intentionally NOT here — run it once from the Render shell
set -euo pipefail
uv run alembic upgrade head
uv run uvicorn reckonflow.main:app --host 0.0.0.0 --port "${PORT:-8000}"
