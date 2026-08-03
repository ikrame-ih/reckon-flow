# Phase 4 — Receipt extraction

## Goal

Upload a receipt, return **202**, extract structured fields in the background.
Treat model output as untrusted data.

## Worked example

```http
POST /api/v1/receipts?expense_id=1
Content-Type: multipart/form-data
file=<hotel.txt>

→ 202 {"id": 1, "status": "pending", ...}

GET /api/v1/receipts/1
→ status=completed, extraction={vendor, amount, currency, date, ...}
```

Without `GROQ_API_KEY` the rule-based stub runs so CI stays offline. With a
key, Groq + PydanticAI fill `ReceiptExtraction` (`extra="forbid"`).

## Eval snapshot (stub)

| Fixture | Fields correct |
| --- | --- |
| hotel_berlin | 7/7 |
| taxi_receipt | 4/4 |
| hotel_noisy | amount + vendor |
| multilingual_fr | amount + date |

Gate in CI: overall field accuracy must stay above the threshold in
`scripts/run_evals.py`.

## What went wrong once

An early prompt said “extract and approve if under policy.” That was removed —
the model has no action fields. Containment is the schema, not the prose.

**Key paths:** `ai/groq_provider.py`, `ai/stub.py`, `evals/`, ADR 002
