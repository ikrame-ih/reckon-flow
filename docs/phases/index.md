# Build phases

ReckonFlow was built in six phases. Each page has a worked example and the
failure mode that matters for that phase.

| Phase | Focus |
| --- | --- |
| [0](00-skeleton.md) | Package layout, `/health`, CI, config, logging |
| [1](01-ledger.md) | Decimal money, double-entry tables, Alembic |
| [2](02-travel.md) | Travel, approvals, expenses, bank CSV |
| [3](03-idempotency.md) | Redis `Idempotency-Key` + cached responses |
| [4](04-receipts.md) | 202 upload, Groq/stub extraction, evals |
| [5](05-reconciliation.md) | Prefilter, RapidFuzz, RRF, `FOR UPDATE` |
| [6](06-polish.md) | OpenAPI, seed, Neon/Render/Upstash, auth |
| [7](07-follow-ups.md) | Redis rate limits; queue / roles / storage next |

Keep the [glossary](../glossary.md) open while you read.
