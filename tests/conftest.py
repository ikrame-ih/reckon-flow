"""I provide the fixtures every test shares

I run the database tests on in-memory SQLite so `uv run pytest` needs no
Docker, no Postgres, and no network. The models are written to create cleanly
on both dialects — the embedding column falls back to JSON, and the FOR UPDATE
clause is only emitted where the dialect implements it
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from reckonflow.core.db import get_db
from reckonflow.main import create_app
from reckonflow.models import Base


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """I hand each test a fresh schema on its own in-memory database

    StaticPool keeps every checkout on the same connection; without it each
    connection would get its own empty `:memory:` database
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
def client(session: AsyncSession) -> Iterator[TestClient]:
    """I give a TestClient whose routes share the test's SQLite session

    I override get_db instead of pointing the app at a test database, so the
    test can inspect rows through the same session the request just wrote
    """

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
