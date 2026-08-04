# ADR 004: API-key auth scope

- **Status:** Accepted
- **Date:** 2026-08-04
- **Phase:** 6

## Context

ReckonFlow exposes mutating finance endpoints (approve, pay, post ledger,
import bank CSV). An unauthenticated public URL is fine for a short-lived
demo, but any finance API needs an access-control answer before it faces
the internet.

## Decision

Require an `X-API-Key` header on **mutating** methods (`POST`/`PUT`/`PATCH`/
`DELETE`) when the `API_KEY` environment variable is set. Reads and
`GET /health` stay open for probes and Swagger exploration. `GET /metrics`
also requires the key when configured — scrape endpoints should not be public.

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

- Production deploys must set `API_KEY` or the surface stays open
- OpenAPI clients need to send the header on writes
- This is a deliberate scope cut, not a claim of production-grade IAM
