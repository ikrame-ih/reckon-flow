#!/usr/bin/env bash
# I start ReckonFlow on Render after applying migrations
# Optional one-shot seed: set SEED_ON_BOOT=true in Render env, deploy once,
# then set it back to false (free tier has no shell)
set -euo pipefail
uv run alembic upgrade head
if [ "${SEED_ON_BOOT:-false}" = "true" ]; then
  uv run python scripts/seed_demo.py || true
fi
uv run uvicorn reckonflow.main:app --host 0.0.0.0 --port "${PORT:-8000}"
