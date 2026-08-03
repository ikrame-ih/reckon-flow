"""I check Neon-style URL rewriting for asyncpg"""

from __future__ import annotations

from reckonflow.core.config import async_database_url


def test_strips_channel_binding_and_uses_asyncpg() -> None:
    raw = (
        "postgresql://user:pass@ep-foo.eu-central-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )
    fixed = async_database_url(raw)
    assert fixed.startswith("postgresql+asyncpg://")
    assert "channel_binding" not in fixed
    assert "sslmode" not in fixed
    assert "ssl=require" in fixed


def test_postgres_scheme_is_rewritten() -> None:
    raw = "postgres://user:pass@localhost:5432/reckonflow"
    fixed = async_database_url(raw)
    assert fixed.startswith("postgresql+asyncpg://")
