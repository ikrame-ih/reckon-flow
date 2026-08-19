# Evaluation

This page is an **inventory**, not a leaderboard. Numbers from the matching
script are for this synthetic set only. Do not paste them into a CV as
production quality.

## What exists

| Capability | Where | Honest note |
| --- | --- | --- |
| Structured LLM output, `extra="forbid"` | [`src/reckonflow/schemas/receipt.py`](https://github.com/ikrame-ih/reckon-flow/blob/main/src/reckonflow/schemas/receipt.py) | Invalid extra fields fail validation instead of landing in the DB |
| Receipt fixtures + stub/Groq eval | [`evals/receipts/`](https://github.com/ikrame-ih/reckon-flow/tree/main/evals/receipts), [`scripts/run_evals.py`](https://github.com/ikrame-ih/reckon-flow/blob/main/scripts/run_evals.py) | Four annotated receipts. Stub extractor when `GROQ_API_KEY` is empty |
| Hybrid matching | [`src/reckonflow/services/reconciliation.py`](https://github.com/ikrame-ih/reckon-flow/blob/main/src/reckonflow/services/reconciliation.py) | SQL prefilter → RapidFuzz → embeddings → RRF (`k=60`) |
| Stub / offline embeddings | [`src/reckonflow/core/embeddings.py`](https://github.com/ikrame-ih/reckon-flow/blob/main/src/reckonflow/core/embeddings.py) | Hashed tokens, L2-normalised. **Not** a neural embedding model |
| Background extraction | [`src/reckonflow/api/v1/receipts.py`](https://github.com/ikrame-ih/reckon-flow/blob/main/src/reckonflow/api/v1/receipts.py), [ADR 005](adr/005-background-tasks.md) | FastAPI `BackgroundTasks`, not a durable queue |
| Row locks on confirm | `ReconciliationService.confirm_match` | `SELECT … FOR UPDATE` where the dialect supports it |
| CI evals | [`.github/workflows/ci.yml`](https://github.com/ikrame-ih/reckon-flow/blob/main/.github/workflows/ci.yml) | Receipt fixtures + matching baselines, every push/PR |

## What does not exist yet

- A **labeled production** bank/expense dataset (no real statements in-tree)
- Reported **recall@k / precision** on live traffic
- **Cost or latency tracing** for Groq calls
- A worker with retries / DLQ (see ADR 005)
- Real vectors on the default path — swap `text_embedding` later without
  changing columns

## Receipt extraction

```bash
uv run python scripts/run_evals.py
```

Uses the stub when Groq is unset so CI stays offline. Field accuracy on four
fixtures is a **smoke check**, not a paper result.

## Matching baselines

```bash
uv run python scripts/run_matching_evals.py
```

Dataset: [`evals/dataset/cases.json`](https://github.com/ikrame-ih/reckon-flow/blob/main/evals/dataset/cases.json)
(40 authored cases). `N` is far too small to claim production matching quality.

The script does **not** open Postgres. It reuses the same date-window and
amount-tolerance rules as `_prefilter`, then ranks with three baselines:

| Baseline | Rank signal |
| --- | --- |
| `fuzzy` | RapidFuzz `token_set_ratio` |
| `embeddings` | Cosine on the **stub** hash vector |
| `hybrid` | RRF over fuzzy + amount/date + stub embedding (same fusion idea as production) |

If the gold row falls outside the date window or amount slack, every baseline
misses that case. That is intentional: the SQL prefilter is part of the system.

Prints `hit@1` / `hit@3` on this file only. Re-run instead of copying numbers
into docs — they will move if the dataset moves.

## Cold start (demo)

The public Render instance is **free tier**. After idle sleep the first request
can take **~50 seconds**. `/health` is liveness; `/ready` checks the database.

A cron ping only helps if the instance is allowed to stay warm (paid / no
sleep). On free Render, sleep still wins. Local `uvicorn` has no cold start.

Optional ping (no secrets):

```bash
curl -fsS https://reckon-flow.onrender.com/health
```
