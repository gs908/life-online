"""DEV-59 契约层(无需数据库):`TaskCreate.ephemeral` 的分流与拒绝口径。

DB/API 行为见 `test_ephemeral_task.py`;这里只钉 schema 层最容易漏的两点 ——
`ephemeral` 默认关闭(旧路径行为不变)、以及"配了却不生效"的模板级字段显式 422。
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.task import TaskCreate


def test_ephemeral_defaults_off_for_legacy_path():
    body = TaskCreate.model_validate({"title": "旧路径"})
    assert body.ephemeral is False
    assert body.target_date is None


def test_ephemeral_accepts_minimal_body():
    body = TaskCreate.model_validate({"title": "临时任务", "ephemeral": True})
    assert body.ephemeral is True
    assert body.type.value == "DAILY"


def test_ephemeral_rejects_template_scoped_fields():
    """没有模板行 → 触发规则/模板库/非 DAILY 类型/时间窗/链式都无处安放。
    一律 422,不静默丢弃(否则家长会以为"配了却没生效")。"""
    cases = [
        {"triggers": [{"kind": "DAILY"}]},
        {"library_id": "00000000-0000-0000-0000-000000000000"},
        {"type": "CHALLENGE"},
        {"timed_mode": "DEADLINE", "deadline_time": "20:00"},
        {"chain_key": "c1", "chain_total": 2},
    ]
    for over in cases:
        with pytest.raises(ValidationError):
            TaskCreate.model_validate({"title": "临时任务", "ephemeral": True, **over})


def test_target_date_only_valid_for_ephemeral():
    with pytest.raises(ValidationError, match="target_date"):
        TaskCreate.model_validate({"title": "旧路径", "target_date": "2026-01-01"})
    # 临时任务接受 target_date,缺省为 None(由服务层回落今天)。
    body = TaskCreate.model_validate({"title": "临时任务", "ephemeral": True, "target_date": "2026-01-01"})
    assert str(body.target_date) == "2026-01-01"