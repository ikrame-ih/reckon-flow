"""I define column types that adapt to the database behind them

I store embeddings as JSON everywhere by default so a native Windows
PostgreSQL install works without the pgvector extension. When I later run
on pgvector/pgvector Docker, I can switch this dialect branch back to Vector
without changing the Python value type (list[float])
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Dialect
from sqlalchemy.types import TypeDecorator, TypeEngine

DEFAULT_EMBEDDING_DIMENSIONS = 384


class EmbeddingVector(TypeDecorator[list[float]]):
    """I persist an embedding as JSON so demos do not require pgvector

    Reconciliation already works on amount, date, and RapidFuzz; embeddings
    only sharpen ranks when present
    """

    impl = JSON
    cache_ok = True

    def __init__(self, dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS) -> None:
        self.dimensions = dimensions
        super().__init__()

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        # JSONB on Postgres is enough for a portfolio demo without extensions
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB

            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())
