"""
异步 SQLAlchemy engine / session factory。

- 应用使用 asyncmy (异步驱动)
- 迁移工具使用 pymysql (同步驱动,见 settings.database.url_sync)
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.common.db.base import Base

engine: AsyncEngine = create_async_engine(
    settings.database.url_async,
    echo=settings.app.debug,
    pool_pre_ping=settings.database.pool.pool_pre_ping,
    pool_recycle=settings.database.pool.pool_recycle,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
    autoflush=False,
)


async def dispose_engine() -> None:
    await engine.dispose()


__all__ = ["Base", "engine", "AsyncSessionLocal", "dispose_engine"]
