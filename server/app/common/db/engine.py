"""
异步 SQLAlchemy engine / session factory。

- 应用使用 asyncpg (异步驱动)
- 迁移工具使用 psycopg (同步驱动,见 settings.database.url_sync)
- Supabase pooler 事务模式(6543 端口,pgbouncer)不支持 asyncpg 的预编译语句,
  会报 "prepared statement ... already exists"。按 SQLAlchemy 官方适配方案:
  关闭语句缓存(statement_cache_size=0)+ NullPool。
  若后续切换会话模式 pooler(5432)或直连,可恢复 QueuePool 与语句缓存。
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import settings
from app.common.db.base import Base

engine: AsyncEngine = create_async_engine(
    settings.database.url_async,
    echo=settings.app.debug,
    connect_args={
        # pgbouncer 事务模式兼容:禁用 asyncpg 预编译语句缓存
        "statement_cache_size": 0,
        **settings.database.async_connect_args,
    },
    poolclass=NullPool,
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
