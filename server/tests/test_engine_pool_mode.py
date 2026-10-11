"""连接池策略单元测试(DEV-29 审查收尾)。

锁定核心不变式:`.env` 指向 6543(事务模式 pooler)时引擎必须按
NullPool + 关闭预编译语句缓存适配;其余端口恢复默认连接池。
不需要数据库连接,只断言 `_build_engine_kwargs()` 的选择结果。
"""
from __future__ import annotations

import pytest
from sqlalchemy.pool import NullPool

from app.common.db.engine import _build_engine_kwargs
from app.config import DatabasePoolSection, settings


def _configure(monkeypatch: pytest.MonkeyPatch, *, port: int, mode: str) -> None:
    monkeypatch.setattr(settings.database, "port", port)
    monkeypatch.setattr(settings.database.pool, "mode", mode)


def test_auto_6543_uses_null_pool_and_disables_statement_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """6543 + auto(现状配置):NullPool + statement_cache_size=0,池参数不注入。"""
    _configure(monkeypatch, port=6543, mode="auto")
    kwargs = _build_engine_kwargs()
    assert kwargs["poolclass"] is NullPool
    assert kwargs["connect_args"]["statement_cache_size"] == 0
    assert "pool_pre_ping" not in kwargs
    assert "pool_recycle" not in kwargs


def test_auto_other_port_uses_default_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 6543 端口 + auto(本地 Docker / 直连 / 会话 pooler):默认池,池参数生效。"""
    _configure(monkeypatch, port=5432, mode="auto")
    kwargs = _build_engine_kwargs()
    assert "poolclass" not in kwargs
    assert kwargs["pool_pre_ping"] is settings.database.pool.pool_pre_ping
    assert kwargs["pool_recycle"] == settings.database.pool.pool_recycle
    assert "statement_cache_size" not in kwargs["connect_args"]


def test_forced_transaction_pooler_overrides_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """显式 transaction_pooler:即使端口不是 6543 也按事务模式适配。"""
    _configure(monkeypatch, port=5432, mode="transaction_pooler")
    kwargs = _build_engine_kwargs()
    assert kwargs["poolclass"] is NullPool
    assert kwargs["connect_args"]["statement_cache_size"] == 0


def test_forced_default_pool_overrides_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """显式 default:即使端口是 6543 也用默认连接池(自担预编译语句兼容性)。"""
    _configure(monkeypatch, port=6543, mode="default")
    kwargs = _build_engine_kwargs()
    assert "poolclass" not in kwargs
    assert "statement_cache_size" not in kwargs["connect_args"]


def test_connect_args_keep_application_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """应用名经 server_settings 传递,不因池模式不同而丢失。"""
    _configure(monkeypatch, port=6543, mode="auto")
    connect_args = _build_engine_kwargs()["connect_args"]
    assert connect_args["server_settings"]["application_name"] == "life-online"


def test_invalid_mode_fails_fast() -> None:
    """mode 是 Literal:typo 在配置加载时即报 ValidationError,不静默回落。"""
    with pytest.raises(Exception, match="transaction_pooler"):
        DatabasePoolSection(mode="transaction-pooler")  # type: ignore[arg-type]
