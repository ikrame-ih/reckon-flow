# Why SQL prefilter + RapidFuzz + RRF

Bank lines and expense forms describe the same payment in different words.
`"TAXI BERLIN 14/09"` is not a join key for `"Airport transfer, Berlin"`.

ReckonFlow does **not** cosine-everything:

1. **SQL prefilter** — date window + amount slack. Without this, fuzzy
   scoring would scan the whole statement.
2. **RapidFuzz `token_set_ratio`** — abbreviations and word order.
3. **Stub embeddings** (hashed tokens) when both sides have a vector.
   This is **not** a neural model.
4. **RRF (`k=60`)** — fuse *rankings*, because RapidFuzz (0–100) and cosine
   (−1–1) are not on one scale.

Wrong silent matches cost more than a review queue. Auto-match still needs a
fuzzy floor, not rank alone.

How to reproduce the toy numbers (do not cite as production):

```bash
uv run python scripts/run_matching_evals.py
```

See [evaluation.md](../evaluation.md).
