"""Shared test fixtures

Database tests use in-memory SQLite so pytest needs no Docker or network.
Models create cleanly on both dialects — embeddings fall back to JSON, and
FOR UPDATE is only emitted where supported.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from reckonflow.core.config import get_settings
from reckonflow.core.db import get_db
from reckonflow.main import create_app
from reckonflow.models import Base


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
