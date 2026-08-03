"""Deterministic text embeddings for hybrid reconciliation

No network call: hash tokens into a fixed-size vector so cosine similarity
works offline and in CI. Swap this for a real embedding model later without
changing the Expense/BankTransaction columns.
"""

from __future__ import annotations

import hashlib
import math
import re

from reckonflow.models.types import DEFAULT_EMBEDDING_DIMENSIONS

_TOKEN = re.compile(r"[a-z0-9]+")


def text_embedding(
    text: str, *, dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS
) -> list[float]:
    """Bag-of-hashed-tokens vector, L2-normalised"""
    vector = [0.0] * dimensions
    tokens = _TOKEN.findall(text.lower())
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]
