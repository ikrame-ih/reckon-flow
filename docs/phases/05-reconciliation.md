# Phase 5 — Reconciliation

## Goal

Suggest bank matches without scanning every statement line, and refuse to
guess when two candidates look equal.

## Worked example (RRF arithmetic)

Expense: `Hotel Adlon / 612.40 EUR / 2026-09-17`

Prefilter keeps two bank rows. Ranks (k=60):

| Candidate | Fuzzy rank | Amount rank | RRF score |
| --- | --- | --- | --- |
| A HOTEL ADLON… | 1 | 1 | 1/61 + 1/61 ≈ **0.0328** |
| B LUFTHANSA… | 2 | 2 | 1/62 + 1/62 ≈ **0.0323** |

A wins. If the top-two RRF scores are within the ambiguity margin, the expense
goes to `pending_review` instead of auto-match.

Confirm uses `SELECT … FOR UPDATE` so two reviewers cannot claim the same
bank line. Currency mismatches are dropped in the prefilter.

## Failure case

Second confirm on an already-matched expense → **409 Conflict**.

RapidFuzz scores (0–100) and embedding cosine (−1–1) are not on one scale, so
RRF merges **ranks** instead of weighted averages. Missing embeddings then
degrade gracefully.

Paths: `services/reconciliation.py`, `core/embeddings.py`
