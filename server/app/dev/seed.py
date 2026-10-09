"""
最小可用的种子数据构造器。

覆盖 家庭 -> 家长 -> 孩子 -> 赛季 -> 任务模板 -> 任务实例 的基础创建链路,
全部通过现有 service 层 / ORM 完成,不绕过业务规则。

用途:
- `tests/conftest.py` 中的冒烟测试 fixture 复用本模块搭建数据,并在用例结束后
  通过 `cleanup_family` 级联清理,不在远程数据库中留下测试脏数据。
- DEV-5(开发阶段非微信登录)可以直接复用 `seed_basic_family` 拿到一组带角色的
  测试账号(`SeededFamily.parent` / `.child`),再配合 `auth_service.issue_token_pair`
  签发 token,不需要重新设计"如何造一个可登录账号"这件事。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TaskType, ThemeId
from app.models.scn_season import ScnSeason
from app.models.scn_task_instance import ScnTaskInstance
from app.models.scn_task_template import ScnTaskTemplate
from app.models.sys_account import SysAccount
from app.models.sys_child import SysChild
from app.models.sys_family import SysFamily
from app.services import family_service


@dataclass
class SeededFamily:
    family: SysFamily
    parent: SysAccount
    child_account: SysAccount
    child: SysChild
    season: ScnSeason
    task_template: ScnTaskTemplate
    task_instance: ScnTaskInstance


async def seed_basic_family(db: AsyncSession, *, suffix: str = "smoke") -> SeededFamily:
    """创建一条最小可用的家庭数据链路,返回链路上每一环的实体。"""
    family = await family_service.create_family(
        db, name=f"测试家庭-{suffix}", owner_name=f"家长-{suffix}"
    )
    parent = await db.get(SysAccount, family.owner_id)
    assert parent is not None, "create_family 应已写入 owner_id 对应的账号"

    child_account = await family_service.create_adventurer(
        db, family_id=family.id, name=f"孩子-{suffix}"
    )
    child = (
        await db.execute(
            select(SysChild).where(SysChild.account_id == child_account.id)
        )
    ).scalar_one()

    season = ScnSeason(
        family_id=family.id,
        name=f"赛季-{suffix}",
        theme_id=ThemeId.DEFAULT,
        start_date=datetime.now(timezone.utc),
        is_active=True,
    )
    db.add(season)
    await db.flush()

    task_template = ScnTaskTemplate(
        family_id=family.id,
        season_id=season.id,
        creator_account_id=parent.id,
        target_child_id=child.id,
        title=f"任务模板-{suffix}",
        type=TaskType.DAILY,
        xp_reward=50,
    )
    db.add(task_template)
    await db.flush()

    task_instance = ScnTaskInstance(
        family_id=family.id,
        season_id=season.id,
        template_id=task_template.id,
        creator_account_id=parent.id,
        target_child_id=child.id,
        assignee_child_id=child.id,
        title=task_template.title,
        xp_reward=task_template.xp_reward,
    )
    db.add(task_instance)
    await db.commit()
    await db.refresh(task_instance)

    return SeededFamily(
        family=family,
        parent=parent,
        child_account=child_account,
        child=child,
        season=season,
        task_template=task_template,
        task_instance=task_instance,
    )


async def cleanup_family(db: AsyncSession, family_id: str) -> None:
    """按 family_id 级联清理种子数据。

    依赖各表 `sys_family.id` 外键上的 `ondelete=CASCADE`,直接 DELETE 家庭行,
    数据库会级联删除账号 / 家长 / 孩子 / 赛季 / 任务模板 / 任务实例等下级数据。
    """
    await db.execute(delete(SysFamily).where(SysFamily.id == family_id))
    await db.commit()
