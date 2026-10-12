"""
scripts/fk_topo_order.py 的单测(纯 metadata,不连数据库)。

覆盖:
- 真实模型的拓扑顺序合法(每张表的非回填外键父表都排在其前);
- 可空循环引用自动选回填边(use_alter 边优先);
- 不可空循环引用明确报错(提示改用 deferrable),而非输出错误顺序。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import Column, ForeignKey, ForeignKeyConstraint, MetaData, String, Table

import app.models  # noqa: F401  确保完整 metadata
from app.common.db.base import Base

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fk_topo_order.py"
_spec = importlib.util.spec_from_file_location("fk_topo_order", _SCRIPT)
fk_topo_order = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("fk_topo_order", fk_topo_order)
_spec.loader.exec_module(fk_topo_order)


def _validate_order(
    order: list[str], metadata: MetaData, backfill: list[tuple[str, str, str]]
) -> None:
    """除回填边外,每条外键的父表都必须排在子表之前。"""
    position = {name: i for i, name in enumerate(order)}
    backfill_set = set(backfill)
    for table in metadata.tables.values():
        for constraint in table.constraints:
            if not isinstance(constraint, ForeignKeyConstraint):
                continue
            for element in constraint.elements:
                referred = element.column.table
                if referred is table:
                    continue
                if (table.name, element.parent.name, referred.name) in backfill_set:
                    continue
                assert position[referred.name] < position[table.name], (
                    f"顺序非法: {table.name} 排在它的父表 {referred.name} 之前"
                )


def test_real_metadata_order_is_valid() -> None:
    order, backfill = fk_topo_order.topo_sort(Base.metadata)
    assert len(order) == 29
    assert order[0] == "sys_family"
    _validate_order(order, Base.metadata, backfill)


def test_real_metadata_backfill_uses_use_alter_edge() -> None:
    """环上唯一 use_alter 边应被选为回填边(DDL 破环边 == 数据导入破环边)。"""
    _order, backfill = fk_topo_order.topo_sort(Base.metadata)
    assert ("sys_child", "onboarding_step_id", "scn_onboarding_step") in backfill


def _make_cycle_metadata(nullable_cycle_column: bool) -> MetaData:
    """三表环 a → b → c → a(每张表都持有指向下一张表的外键);环边 c.a_id 可空性可调。"""
    metadata = MetaData()
    Table(
        "a", metadata,
        Column("id", String(36), primary_key=True),
        Column("b_id", String(36), ForeignKey("b.id"), nullable=False),
    )
    Table(
        "b", metadata,
        Column("id", String(36), primary_key=True),
        Column("c_id", String(36), ForeignKey("c.id"), nullable=False),
    )
    Table(
        "c", metadata,
        Column("id", String(36), primary_key=True),
        Column("a_id", String(36), ForeignKey("a.id"), nullable=nullable_cycle_column),
    )
    return metadata


def test_nullable_cycle_is_broken_with_backfill() -> None:
    metadata = _make_cycle_metadata(nullable_cycle_column=True)
    order, backfill = fk_topo_order.topo_sort(metadata)
    assert len(order) == 3
    assert backfill, "可空环应有回填边"
    _validate_order(order, metadata, backfill)


def test_not_null_cycle_raises_instead_of_emitting_bad_order() -> None:
    metadata = _make_cycle_metadata(nullable_cycle_column=False)
    with pytest.raises(ValueError, match="deferrable"):
        fk_topo_order.topo_sort(metadata)


def test_use_alter_does_not_bypass_nullability_check() -> None:
    """审查整改(DEV-31):use_alter=True 只是排序优先,不得绕过可空性过滤。

    环上一条 use_alter=True 且 NOT NULL 的边,必须报错而不是输出"先置 NULL"
    的不可行回填方案。
    """
    metadata = MetaData()
    Table(
        "a", metadata,
        Column("id", String(36), primary_key=True),
        Column("b_id", String(36), ForeignKey("b.id", use_alter=True), nullable=False),
    )
    Table(
        "b", metadata,
        Column("id", String(36), primary_key=True),
        Column("a_id", String(36), ForeignKey("a.id"), nullable=False),
    )
    with pytest.raises(ValueError, match="deferrable"):
        fk_topo_order.topo_sort(metadata)


def test_cli_modes_emit_valid_output(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """--reverse / --layers 两种输出模式:行集合与正向一致、格式正确。"""
    forward, backfill = fk_topo_order.topo_sort(Base.metadata)

    monkeypatch.setattr(sys, "argv", ["fk_topo_order.py", "--reverse"])
    fk_topo_order.main()
    reversed_out = capsys.readouterr().out.splitlines()
    assert [ln for ln in reversed_out if not ln.startswith("#")] == list(reversed(forward))

    monkeypatch.setattr(sys, "argv", ["fk_topo_order.py", "--layers"])
    fk_topo_order.main()
    layers_out = capsys.readouterr().out
    assert layers_out.count("\n") >= 6
    assert "第 1 层: sys_family" in layers_out
    # 分层视图不丢表:去掉表名外的分隔后,表数量与正向一致
    named = [part.strip() for ln in layers_out.splitlines() if ln.startswith("第")
             for part in ln.split(":", 1)[1].split(",")]
    assert sorted(named) == sorted(forward)
