"""Async SQLAlchemy engine and session factory

get_db() is a FastAPI dependency — one session per request with clean commit/rollback.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from reckonflow.core.config import async_database_url, get_settings

_settings = get_settings()

engine: AsyncEngine = create_async_engine(
    async_database_url(_settings.database_url),
    echo=_settings.debug,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Request-scoped session; rolls back on unhandled errors"""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
