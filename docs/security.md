# Security

What was checked, what was fixed, and how to re-run the checks.

## Threat model (short)

ReckonFlow is a headless financial API. Attackers might try to:

- inject SQL through query parameters or CSV fields
- escape the upload directory with crafted filenames
- smuggle instructions through receipt text into the extractor
- corrupt money with floats
- double-post via retries
- race two reconcile workers onto the same expense

## Findings and fixes

| Area | Severity | Status | Notes |
| --- | --- | --- | --- |
| SQL injection | High if present | **OK** | Queries use SQLAlchemy `select`/`where` with bound parameters. No f-string SQL found. |
| Path traversal on receipts | High | **Fixed/hardened** | `safe_filename()` strips path segments; `_resolve_storage_path()` ensures the final path stays under `receipt_storage_dir` on write and read. |
| Prompt injection via receipts | Medium | **Mitigated** | `ReceiptExtraction` uses `extra="forbid"`; extractor cannot approve/pay/post. See [ADR 002](adr/002-receipt-untrusted-input.md). |
| Float money | High | **OK** | `MoneyStr` + `parse_money` reject `float`. |
| Secrets in repo | High | **OK** | `.env` gitignored; config from environment. Rotate any secret that was ever pasted into a chat or screenshot. |
| Auth | High | **Mitigated** | Mutating routes require `X-API-Key` when `API_KEY` is set (ADR 004). Empty key disables the gate for local/CI. |
| Duplicate POSTs | Medium | **Mitigated** | Idempotency middleware; fails open if Redis is down (availability over strictness — see ADR 003). |
| Concurrent match writes | Medium | **Mitigated** | `FOR UPDATE` when linking expense ↔ bank row; unique constraints on match links. |
| Rate limiting | Low | **Mitigated** | In-process sliding window (`RATE_LIMIT_PER_MINUTE`); Redis token bucket for multi-instance later. |
| Dependency CVEs | Medium | **OK** | CI runs `pip-audit` on every push; local package is skipped. |
| Debug in production | Low | **OK if configured** | Default `DEBUG=false`; set `APP_ENV=production` on Render. |
| CORS | Low | **N/A** | No browser frontend; default FastAPI CORS is closed unless you add middleware. |

## How to reproduce the checks

```bash
# Same gates as CI
uv run ruff check src tests
uv run mypy src
uv run pytest
uv run pip-audit
uv run python scripts/run_evals.py
```

Manual review checklist:

1. Grep for `text(f"` / string-built SQL — should be empty.
2. Upload a receipt named `../../tmp/evil.txt` — stored name must be sanitized;
   path must remain under storage.
3. Post unbalanced ledger JSON — must fail validation or service rules.
4. Replay `POST` with the same `Idempotency-Key` when Redis is configured.

## Accepted risks

- **Idempotency fail-open:** if Redis is unreachable, retries are not shielded.
  Prefer fixing Redis over flipping this to fail-closed for a public demo API.
- **Free-tier cold starts:** not a security issue, but availability is limited.
- **Shared Upstash DB:** safe if key prefixes differ (`REDIS_KEY_PREFIX`).
