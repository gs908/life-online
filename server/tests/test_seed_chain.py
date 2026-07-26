"""
种子数据创建链路测试。

直接对 `seeded_family` fixture(复用 `app/dev/seed.seed_basic_family`)产出的实体做断言,
覆盖 家庭 -> 家长 -> 孩子 -> 赛季 -> 任务模板 -> 任务实例 的基础创建链路是否正确串联。

需要可连接的数据库(远程优先),不可达时该模块内用例会被 `db_ready` fixture 跳过。
"""
from __future__ import annotations

import pytest

from app.dev.seed import SeededFamily

pytestmark = pytest.mark.db


async def test_seed_chain_is_linked_end_to_end(seeded_family: SeededFamily) -> None:
    seeded = seeded_family

    assert seeded.parent.id == seeded.family.owner_id

    assert seeded.child.account_id == seeded.child_account.id
    assert seeded.child.family_id == seeded.family.id

    assert seeded.season.family_id == seeded.family.id

    assert seeded.task_template.family_id == seeded.family.id
    assert seeded.task_template.season_id == seeded.season.id
    assert seeded.task_template.creator_account_id == seeded.parent.id
    assert seeded.task_template.target_child_id == seeded.child.id

    assert seeded.task_instance.family_id == seeded.family.id
    assert seeded.task_instance.season_id == seeded.season.id
    assert seeded.task_instance.template_id == seeded.task_template.id
    assert seeded.task_instance.creator_account_id == seeded.parent.id
    assert seeded.task_instance.target_child_id == seeded.child.id
    assert seeded.task_instance.assignee_child_id == seeded.child.id
