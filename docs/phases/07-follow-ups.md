# Follow-ups after phases 0–6

Shipped: Redis rate limiting with in-memory fallback (ADR 006).

Still open (pick one at a time):

1. Durable receipt queue (arq / Celery) instead of BackgroundTasks — ADR 005
2. API-key roles (read vs write) beyond a single shared key — ADR 004
3. Object storage for receipts (S3-compatible) instead of local disk
