# Matching dataset

Synthetic expense ↔ bank-line cases for
`uv run python scripts/run_matching_evals.py`.

**N = 40.** That is too small to claim production matching quality. Labels
were written by hand. There are no real bank files in this folder.

Gold is the `gold_id` candidate. Decoys include same-amount merchants,
same-city hotels, and IATA / SMS-style truncations.

Some cases are meant to **fail the prefilter** (amount slack or date window),
because that is how the live pipeline drops rows before RapidFuzz.

Embeddings used by the eval are the hashed-token stub in
`reckonflow.core.embeddings`, not a hosted model.
