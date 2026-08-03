"""I own the async SQLAlchemy engine and session factory

I expose get_db() as a FastAPI dependency so each request gets one session
and commits or rolls back cleanly
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
    """I yield a request-scoped session and roll back on unhandled errors"""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
