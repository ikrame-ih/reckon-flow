# Contributing to ReckonFlow

Thanks for reading the code. A few conventions keep the project readable.

## Comments and docstrings

- Prefer short comments that explain **why** (a constraint, a risk, or a
  design choice), not a restatement of the next line.
- Write in plain English. First person is fine when it sounds natural;
  otherwise use a clear third-person note.

## Code layout

| Package | Role |
| --- | --- |
| `api/` | HTTP routers and middleware |
| `services/` | Business rules |
| `models/` | SQLAlchemy tables |
| `schemas/` | Pydantic request/response shapes |
| `ai/` | Receipt extractors (Groq or stub) |
| `core/` | Settings, DB, money helpers, logging |

Money crosses the API as **JSON strings**, never floats.

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

## Docs site

Project documentation (phases, glossary, ADRs) lives under `docs/` and is
built with MkDocs Material → [GitHub Pages](https://ikrame-ih.github.io/reckon-flow/).
