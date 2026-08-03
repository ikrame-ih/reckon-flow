# Phase 6 — Polish and deploy

## What was built

- Richer OpenAPI descriptions and examples (Swagger as the demo UI)
- Idempotent `scripts/seed_demo.py`
- `scripts/render_start.sh` — migrations on boot
- Neon (Postgres) + Render (API) + Upstash (Redis)
- URL rewriting so Neon’s `channel_binding` query param does not break asyncpg
- This documentation site (MkDocs Material → GitHub Pages)

## Why

A headless API needs a public `/docs` link more than a custom frontend. Seed
data lets a visitor see real accounts without crafting JSON from scratch.

## How to demo

1. Open the [live docs](https://reckon-flow.onrender.com/docs)
2. Hit `/health`, then `/api/v1/accounts`
3. Post a balanced ledger transaction (amounts as strings)
4. With `GROQ_API_KEY` set, upload a receipt and poll until `extracted`

Cold starts on free Render can take ~50 seconds — that is expected.
