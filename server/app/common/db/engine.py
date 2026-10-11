"""
异步 SQLAlchemy engine / session factory。

- 应用使用 asyncpg (异步驱动)
- 迁移工具使用 psycopg (同步驱动,见 settings.database.url_sync)
- Supabase pooler 事务模式(6543 端口,pgbouncer/supavisor)不支持 asyncpg 的
  预编译语句,会报 "prepared statement ... already exists"。按 SQLAlchemy 官方
  适配方案:关闭语句缓存(statement_cache_size=0)+ NullPool。
- 连接池策略由 `config.yaml` 的 `database.pool.mode` 控制(默认 `auto`):
  6543 → 事务模式适配;其他端口(本地 Docker / 直连 / 会话模式 pooler)→
  默认连接池 + 语句缓存。详见 docs/11-数据库连接调优.md。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.common.db.base import Base
from app.config import settings

#: Supabase 事务模式 pooler 的固定端口(supavisor/pgbouncer transaction mode)
TRANSACTION_POOLER_PORT = 6543


def _is_transaction_pooler() -> bool:
    """是否需要按事务模式 pooler 适配(NullPool + 关闭预编译语句)。"""
    mode = settings.database.pool.mode
    if mode == "transaction_pooler":
        return True
    if mode == "default":
        return False
    # auto:按端口判定
    return settings.database.port == TRANSACTION_POOLER_PORT


def _build_engine_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    connect_args: dict[str, Any] = {}
    if _is_transaction_pooler():
        kwargs["poolclass"] = NullPool
        # pgbouncer 事务模式兼容:禁用 asyncpg 预编译语句缓存
        connect_args["statement_cache_size"] = 0
    else:
        # 默认连接池(AsyncAdaptedQueuePool)下,池参数恢复生效
        kwargs["pool_pre_ping"] = settings.database.pool.pool_pre_ping
        kwargs["pool_recycle"] = settings.database.pool.pool_recycle
    kwargs["connect_args"] = {**connect_args, **settings.database.async_connect_args}
    return kwargs


engine: AsyncEngine = create_async_engine(
    settings.database.url_async,
    echo=settings.app.debug,
    **_build_engine_kwargs(),
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
    autoflush=False,
)


async def dispose_engine() -> None:
    await engine.dispose()


__all__ = ["AsyncSessionLocal", "Base", "dispose_engine", "engine"]
