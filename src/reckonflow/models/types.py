"""Column types that adapt to the database behind them

Embeddings default to JSON so native Windows PostgreSQL works without pgvector.
On pgvector/pgvector Docker the dialect branch can switch to Vector without
changing the Python value type (list[float]).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Dialect
from sqlalchemy.types import TypeDecorator, TypeEngine

DEFAULT_EMBEDDING_DIMENSIONS = 384


class EmbeddingVector(TypeDecorator[list[float]]):
    """Persist embeddings as JSON — demos do not require pgvector"""

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
