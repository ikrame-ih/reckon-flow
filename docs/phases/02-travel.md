# Phase 2 — Travel flow

## Goal

Trip pre-request → approval state machine → expenses → bank CSV import.

## Worked example

```http
POST /api/v1/travel-requests
{
  "employee_name": "Ada Lovelace",
  "destination": "Berlin",
  "purpose": "Conference",
  "start_date": "2026-09-14",
  "end_date": "2026-09-17",
  "estimated_amount": "500.00",
  "currency": "EUR"
}
# → approval.status = pending

POST /api/v1/approvals/{id}/transition
{"action": "approve", "reviewer": "finance.lead"}

POST /api/v1/expenses
{
  "travel_request_id": 1,
  "vendor": "Hotel Mitte",
  "description": "3 nights Berlin",
  "amount": "120.00",
  "expense_date": "2026-09-15",
  "currency": "EUR"
}
```

`mark_paid` posts a balanced ledger transaction (TRAVEL debit / CASH credit)
using the trip's estimated amount. Expenses on a still-pending trip are
rejected — spend only attaches after approval.

## Failure case

```http
POST .../transition  {"action": "mark_paid"}   # while still pending
→ 409 InvalidStateTransitionError
```

## What went wrong once

Expenses originally linked to any trip id. Rejected trips still accepted
spend. The approval-status check closed that hole.

**Key paths:** `services/travel.py`, `services/bank.py`, `api/v1/approvals.py`
