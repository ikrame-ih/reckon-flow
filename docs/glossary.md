# Glossary

Plain-language definitions for terms used in ReckonFlow.

## Idempotency

Doing the same request more than once has the **same effect** as doing it once.
If a client posts an expense, times out, and retries, the second call should
not create a second expense.

## SET NX EX 86400

Redis command pieces:

- **SET** — write a key/value
- **NX** — only write if the key does **n**ot yet e**x**ist
- **EX 86400** — expire the key after 86 400 seconds (24 hours)

ReckonFlow uses this to *claim* an `Idempotency-Key` in one atomic step. The
first caller owns the key; a retry finds it already set and gets the cached
response instead of running the handler again.

## Double-entry ledger

Every movement of money is recorded as at least two lines: something is
**debited**, something else is **credited**, and the totals cancel to zero.
That invariant is what “the books balance” means.

## Append-only ledger

Past ledger rows are not updated or deleted. A mistake is fixed by posting a
new **reversing** transaction that cancels the bad one. History stays intact.

## Reverse entry / reversing transaction

A new balanced transaction that undoes a previous one (swap debits and
credits, or post opposite signs according to the chart of accounts). Used
instead of editing old rows.

## MoneyStr

Pydantic type / convention: money arrives and leaves the API as a **JSON
string** (`"120.50"`), not a JSON number. Numbers in JSON become floats in
many clients, and floats are unsafe for money.

## Decimal

Python’s exact base-10 number type. ReckonFlow parses money into `Decimal`
and stores `NUMERIC(15, 4)` in Postgres.

## Fail-open (idempotency)

If Redis is down, the middleware logs a warning and **lets the request
through**. Availability wins over retry protection for that moment. Documented
as an intentional trade-off.

## Connection pool

A small set of reusable database connections. Opening a TCP connection to
Postgres for every request is slow; the pool keeps a few warm.

## Migration (Alembic)

Versioned scripts that change the database schema (create tables, add
constraints). `alembic upgrade head` applies everything not yet applied.

## extra="forbid"

Pydantic setting: if the JSON contains a field the schema does not declare,
validation **fails**. Used on receipt extraction so a model cannot smuggle
unexpected keys into storage.

## Prompt injection

Malicious text inside user content (here: a receipt) that tries to make a
language model ignore its instructions. ReckonFlow mitigates this by letting
the model fill **data only**, never trigger approvals or payments.

## Prefilter

Cheap SQL filters (date window, amount tolerance) that shrink the candidate
set **before** fuzzy or embedding search runs.

## RapidFuzz

Library for fuzzy string similarity (typos, reordered tokens). Used to rank
bank descriptions against expense text.

## Embeddings

Numeric vectors that represent text meaning. Optional in ReckonFlow; stored
as JSON on stock Postgres so a Windows install does not need the pgvector
extension.

## pgvector

PostgreSQL extension for storing and searching vectors efficiently. The Docker
image `pgvector/pgvector` includes it; the portable schema uses JSONB instead
when the extension is unavailable.

## RRF (Reciprocal Rank Fusion), k=60

Algorithm that merges several ranked lists. For each item it adds
`1 / (k + rank)` from each list. **k=60** is a common constant that softens
the weight of top ranks. Useful because RapidFuzz scores and embedding scores
are not on the same scale — RRF only cares about **order**.

## FOR UPDATE

SQL row lock: `SELECT … FOR UPDATE` locks the selected rows until the
transaction ends. ReckonFlow uses it when linking an expense to a bank line so
two workers cannot claim the same expense at once.

## 202 Accepted

HTTP status: the request was accepted for processing, but work continues in
the background. Receipt uploads return 202 so the client is not blocked on a
model call.
