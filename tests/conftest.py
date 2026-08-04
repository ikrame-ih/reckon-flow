"""Shared test fixtures

Default database tests use in-memory SQLite so pytest needs no Docker.
Postgres-marked tests use DATABASE_URL when it points at PostgreSQL (CI
service, or a local instance).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool

from reckonflow.core.config import async_database_url, get_settings
from reckonflow.core.db import get_db
from reckonflow.main import create_app
from reckonflow.models import Base


def _postgres_url() -> str | None:
    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        return None
    url = async_database_url(raw)
    if "postgresql" not in url:
        return None
    return url


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Fresh in-memory schema per test

    StaticPool keeps every checkout on one connection; otherwise each connection
    gets its own empty :memory: database.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db_session:
        yield db_session

    await engine.dispose()


@pytest_asyncio.fixture
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    """Engine bound to CI/local Postgres; skips when unavailable"""
    url = _postgres_url()
    if url is None:
        pytest.skip("DATABASE_URL is not a PostgreSQL URL")

    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — connection probe
        await engine.dispose()
        pytest.skip(f"PostgreSQL unreachable: {exc}")

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Session on a truncated Postgres schema (migrations applied in CI)"""
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE ledger_entries, ledger_transactions, receipts, "
                "bank_transactions, expenses, approvals, travel_requests, "
                "accounts RESTART IDENTITY CASCADE"
            )
        )

    maker = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db_session:
        yield db_session
        await db_session.rollback()


@pytest.fixture
def client(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """TestClient sharing the test SQLite session via get_db override

    Override lets the test inspect rows through the same session the request wrote.
    """
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("METRICS_ENABLED", "false")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()
