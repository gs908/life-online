"""
开发期非微信登录:按角色获取一个可复用的开发测试账号。

- 固定挂在一个名为“开发环境”的家庭下,同一角色重复调用返回同一个账号(幂等),
  不会每次登录都在数据库里堆一条新家庭 / 新账号。
- 全部通过 `family_service` 现有的家庭 / 账号创建逻辑完成,不绕过业务规则,
  复用 DEV-4 里已经验证过的 `auth_service.issue_token_pair` 来签发 token。
- 仅供 `DEV_LOGIN_ENABLED=true` 时的开发登录接口调用,不在生产路径上使用。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.models.sys_account import SysAccount
from app.models.sys_family import SysFamily
from app.services import family_service

DEV_FAMILY_NAME = "开发环境"
DEV_PARENT_NAME = "开发家长"
DEV_CHILD_NAME = "开发孩子"


async def _get_or_create_dev_family(db: AsyncSession) -> SysFamily:
    result = await db.execute(select(SysFamily).where(SysFamily.name == DEV_FAMILY_NAME))
    family = result.scalar_one_or_none()
    if family is not None:
        return family
    return await family_service.create_family(db, name=DEV_FAMILY_NAME, owner_name=DEV_PARENT_NAME)


async def get_or_create_dev_user(
    db: AsyncSession, *, role: UserRole, name: str | None = None
) -> SysAccount:
    """按角色返回一个固定的开发测试账号,不存在则创建。"""
    family = await _get_or_create_dev_family(db)

    if role == UserRole.GUILD_MASTER:
        owner = await db.get(SysAccount, family.owner_id)
        assert owner is not None, "开发家庭的 owner_id 应始终指向一个已存在的账号"
        return owner

    result = await db.execute(
        select(SysAccount)
        .where(SysAccount.family_id == family.id, SysAccount.role == UserRole.ADVENTURER.value)
        .order_by(SysAccount.id)
    )
    child_account = result.scalars().first()
    if child_account is not None:
        return child_account
    return await family_service.create_adventurer(
        db, family_id=family.id, name=name or DEV_CHILD_NAME
    )
