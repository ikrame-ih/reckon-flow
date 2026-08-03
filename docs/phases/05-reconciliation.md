# Phase 5 — Reconciliation

## What was built

- SQL prefilter (date window + amount tolerance)
- RapidFuzz ranking on descriptions
- Optional embedding ranks when vectors are present
- Reciprocal Rank Fusion with **k = 60**
- Auto-match above a confidence threshold; otherwise `pending_review`
- `SELECT … FOR UPDATE` when linking expense ↔ bank row

## Why

Bank lines and expenses rarely share a primary key. Exact joins fail. Ranking
candidates and leaving low-confidence cases for humans is the practical design.

## How it works

Prefilter first so fuzzy matching never scans the whole statement. RRF merges
rank lists without forcing every score into the same numeric scale. Glossary:
**RapidFuzz**, **RRF**, **FOR UPDATE**, **prefilter**.

**Key paths:** `services/reconciliation.py`, `api/v1/reconciliation.py`
