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
from the sum of linked expenses when present, otherwise the trip estimate.
Expenses on a still-pending trip are rejected — spend only attaches after
approval.

## Failure case

```http
POST .../transition  {"action": "mark_paid"}   # while still pending
→ 409 InvalidStateTransitionError
```

The approval-status check is what stops spend attaching to a rejected or
still-pending trip.

Paths: `services/travel.py`, `services/bank.py`, `api/v1/approvals.py`
