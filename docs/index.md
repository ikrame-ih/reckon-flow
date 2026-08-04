# ReckonFlow

<div class="rf-hero" markdown="1">

Headless FastAPI backend for corporate travel: pre-approvals, an immutable
double-entry ledger, structured receipt extraction, and hybrid bank
reconciliation.

**[Live API (Swagger)](https://reckon-flow.onrender.com/docs)** ·
**[GitHub](https://github.com/ikrame-ih/reckon-flow)**

There is no product UI — Swagger is the interactive demo. Free Render
instances may take ~50s on the first request after sleep.

</div>

Request path in one line: client → idempotency middleware (Redis) → routers →
services → Postgres; receipt uploads return **202** and extract in the
background (Groq or stub). Matching uses SQL prefilter + RapidFuzz + RRF.

<div class="rf-cards" markdown="1">

<a href="getting-started.md"><strong>Getting started</strong><span>Clone, migrate, seed, run</span></a>
<a href="phases/index.md"><strong>Build phases</strong><span>Ledger → travel → recon</span></a>
<a href="glossary.md"><strong>Glossary</strong><span>Idempotency, RRF, MoneyStr…</span></a>
<a href="security.md"><strong>Security</strong><span>Checks and accepted risks</span></a>
<a href="adr/README.md"><strong>ADRs</strong><span>Why these trade-offs</span></a>

</div>
