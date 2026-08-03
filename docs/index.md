# ReckonFlow

ReckonFlow is a **headless** FastAPI backend for corporate travel:

- pre-approvals for trips
- an immutable **double-entry ledger**
- structured **receipt extraction**
- hybrid **bank reconciliation**

There is no product UI. The interactive demo is Swagger:

**[Live API docs](https://reckon-flow.onrender.com/docs)**

```mermaid
flowchart TD
  Client[API client] --> MW[Idempotency middleware]
  MW --> Redis[(Redis)]
  MW --> API[FastAPI routers]
  API --> Services[Service layer]
  Services --> PG[(PostgreSQL)]
  API -->|202| BG[Background extraction]
  BG --> Extractor[Groq or stub]
  Extractor --> Services
  Services --> Recon[SQL + RapidFuzz + RRF]
  Recon --> PG
```

## Contents

- [Getting started](getting-started.md)
- [Build phases](phases/index.md)
- [Glossary](glossary.md)
- [Security notes](security.md)
