# Contributing

## Layout

| Package | Role |
| --- | --- |
| `api/` | HTTP routers and middleware |
| `services/` | Business rules |
| `models/` | SQLAlchemy tables |
| `schemas/` | Pydantic request/response shapes |
| `ai/` | Receipt extractors (Groq or stub) |
| `core/` | Settings, DB, money helpers, logging |

Money crosses the API as JSON strings, never floats. Prefer short comments
that explain a constraint or risk, not a restatement of the next line.

## Local checks

```bash
uv sync
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest
uv run pip-audit
uv run python scripts/run_evals.py
```

Docs: [GitHub Pages](https://ikrame-ih.github.io/reckon-flow/) (`docs/` → MkDocs Material).
