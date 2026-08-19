# Phase 4 — Receipt extraction

## Goal

Upload a receipt, return **202**, extract structured fields in the background.
Treat model output as untrusted data.

## Worked example

```http
POST /api/v1/receipts
Content-Type: multipart/form-data
file=<hotel.txt>
expense_id=1

→ 202 {"receipt_id": 1, "status": "uploaded", "queue": "arq"|"inline",
       "poll_url": "/api/v1/receipts/1"}

GET /api/v1/receipts/1
→ status=extracted|failed|processing|uploaded

GET /api/v1/receipts/runs
→ recent extraction_runs (duration_ms, provider, outcome; token_count null)
```

Uploads are **plain text / OCR text only** (not PDF or images). Size is checked
before the whole body is buffered.

Without `GROQ_API_KEY` the rule-based stub runs so CI stays offline. With a
key, Groq + PydanticAI fill `ReceiptExtraction` (`extra="forbid"`). Default
model is `openai/gpt-oss-20b` via `GROQ_MODEL` (override anytime). CI evals
score the stub; run `scripts/run_evals.py` locally with a key to check the
live provider.

## Eval snapshot (stub)

| Fixture | Fields correct |
| --- | --- |
| hotel_berlin | 7/7 |
| taxi_receipt | 4/4 |
| hotel_noisy | amount + vendor |
| multilingual_fr | amount + date |

Gate in CI: overall field accuracy must stay above the threshold in
`scripts/run_evals.py`. The model only fills `ReceiptExtraction` — it has no
fields that can approve or pay. Containment is the schema (`extra="forbid"`),
not prompt wording. See ADR 002.

Paths: `ai/groq_provider.py`, `ai/stub.py`, `evals/`, `worker.py`, ADR 007.
