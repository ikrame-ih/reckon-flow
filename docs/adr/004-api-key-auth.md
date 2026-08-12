# ADR 004: API-key auth scope

- **Status:** Accepted (amended)
- **Date:** 2026-08-04
- **Amended:** 2026-08-12
- **Phase:** 6

## Context

ReckonFlow exposes finance endpoints (travel, expenses, bank lines, receipts,
reconciliation, ledger). An unauthenticated public URL is fine for a short-lived
local demo, but any finance API needs an access-control answer before it faces
the internet — including **reads** of employee names and spend data.

## Decision

Require an `X-API-Key` header on **all** `/api/v1` finance routes (GET and
mutating methods) when the `API_KEY` environment variable is set.

Public without a key:

- `/health` (liveness) and `/ready` (readiness)
- Interactive docs (`/docs`, `/swagger`, `/redoc`) and `/openapi.json`

`GET /metrics` also requires the key when configured.

Additional production rule: if `APP_ENV=production` and `API_KEY` is empty,
the process **refuses to start**.

- Empty `API_KEY` disables the gate (local development and CI).
- Keys are compared with `secrets.compare_digest` to avoid timing leaks.
- There are no roles, tenants, or ownership checks yet — the key is a single
  shared secret, not a user identity.

## What real auth would look like next

1. OAuth2 / OIDC (Clerk, Auth0, or company IdP) issuing JWTs
2. Roles: `employee` (create requests), `reviewer` (approve/reject),
   `finance` (pay + reconcile)
3. Ownership: an expense belongs to a user/org; list endpoints filter by it
4. Rotate keys without downtime (dual-key window)

## Consequences

- Production deploys must set `API_KEY` or the app will not boot
- OpenAPI clients need to send the header on finance calls
- This is a deliberate scope cut, not a claim of production-grade IAM
