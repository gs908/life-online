"""
Pytest 全局配置。

- 在任何 `app.*` 模块被 import 之前,为必填的环境变量注入开发期占位默认值,
  确保 `uv run pytest` 在没有真实 `.env` 的干净环境下也能跑通(现有 `Settings`
  对 `jwt.secret` / `llm.*` 没有默认值,缺失会在 import `app.config` 时直接报错)。
  已经配置了真实 `.env` / 环境变量的开发者不受影响:这里只 `setdefault`,不覆盖。
- 数据库相关 fixture 按"远程数据库优先"口径实现:先探测配置的数据库是否可达,
  不可达就跳过依赖 DB 的用例,不在本机拉起 Docker 做实机验证。
"""
from __future__ import annotations

import os

_TEST_ENV_DEFAULTS = {
    "JWT_SECRET": "test-only-secret-do-not-use-in-prod",
    "LLM_BASE_URL": "http://127.0.0.1:0/mock",
    "LLM_API_KEY": "test-key",
    "LLM_MODEL": "test-model",
}
for _key, _value in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(_key, _value)

from collections.abc import AsyncIterator  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.common.db.engine import AsyncSessionLocal, engine  # noqa: E402
from app.dev.seed import SeededFamily, cleanup_family, seed_basic_family  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture(scope="session")
async def db_ready() -> bool:
    """探测配置的数据库(远程优先)是否可达;不可达则跳过依赖 DB 的用例。"""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - 探测阶段允许宽泛捕获,统一转成 skip
        pytest.skip(
            "数据库不可达,跳过 DB 相关冒烟测试(远程数据库优先,本地不做 Docker 实机验证): "
            f"{exc!r}"
        )
    return True


@pytest_asyncio.fixture
async def db_session(db_ready: bool) -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
        await session.close()


@pytest_asyncio.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    """不启动真实 uvicorn 进程,直接对 ASGI app 发请求。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def seeded_family(db_session: AsyncSession) -> AsyncIterator[SeededFamily]:
    """家庭 -> 家长 -> 孩子 -> 赛季 -> 任务模板 -> 任务实例 的基础创建链路。

    用例结束后级联清理,不在远程数据库中留下测试脏数据。
    """
    seeded = await seed_basic_family(db_session, suffix="smoke")
    try:
        yield seeded
    finally:
        await cleanup_family(db_session, seeded.family.id)
