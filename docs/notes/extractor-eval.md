# How the extractor is measured (and what failed)

Two harnesses:

| Harness | Command | What it is |
| --- | --- | --- |
| Receipt fields | `uv run python scripts/run_evals.py` | 4 annotated fixtures. Stub when `GROQ_API_KEY` is empty. |
| Bank matching | `uv run python scripts/run_matching_evals.py` | 40 authored cases. Three baselines. |

**N is small.** Do not put hit rates on a CV.

What the matching run is allowed to show:

- Hybrid (RRF) should be in the same band as fuzzy, usually a little better.
- Stub embeddings should **not** crush fuzzy — they are hashes.
- A few gold rows **should** miss the prefilter (VAT gross vs net, date
  outside the window). That is the SQL stage working, not a bug.

Token usage is not traced yet: `GET /api/v1/receipts/runs` stores
`duration_ms`, provider, outcome, attempt. `token_count` is null.

The model still cannot approve or pay anything (`extra="forbid"`, ADR 002).
