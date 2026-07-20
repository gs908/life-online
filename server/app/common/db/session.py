"""
数据库会话 / 依赖。

- get_db: FastAPI 依赖,提供一个 AsyncSession(自动提交/回滚/关闭)
- DBSession: 类型别名
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db.engine import AsyncSessionLocal

DBSession = AsyncSession


async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
