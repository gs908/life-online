"""特权解锁与使用服务。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.models.enums import UserRole
from app.models.scn_privilege_template import ScnPrivilegeTemplate
from app.models.scn_privilege_unlock import ScnPrivilegeUnlock
from app.models.scn_privilege_use import ScnPrivilegeUse
from app.models.sys_account import SysAccount
from app.models.sys_child import SysChild


def enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


async def ensure_child(db: AsyncSession, *, family_id: str, child_id: str) -> SysChild:
    child = await db.get(SysChild, child_id)
    if child is None:
        child = (
            await db.execute(select(SysChild).where(SysChild.account_id == child_id))
        ).scalar_one_or_none()
    if not child:
        raise NotFoundError(f"孩子 {child_id} 不存在")
    if child.family_id != family_id:
        raise PermissionDeniedError("只能操作自己家庭成员的特权")
    return child


async def unlock_for_user(db: AsyncSession, user: SysChild | SysAccount) -> list[ScnPrivilegeUnlock]:
    """按当前等级补齐孩子已达到等级的特权。"""
    if isinstance(user, SysAccount):
        if enum_value(user.role) != UserRole.ADVENTURER.value:
            return []
        child = (
            await db.execute(select(SysChild).where(SysChild.account_id == user.id))
        ).scalar_one_or_none()
        if child is None:
            return []
    else:
        child = user

    privileges = list((await db.execute(
        select(ScnPrivilegeTemplate).where(
            or_(ScnPrivilegeTemplate.family_id == child.family_id, ScnPrivilegeTemplate.is_system.is_(True)),
            ScnPrivilegeTemplate.level_required <= child.level,
            ScnPrivilegeTemplate.is_active.is_(True),
        )
    )).scalars().all())
    if not privileges:
        return []

    existing_ids = set((await db.execute(
        select(ScnPrivilegeUnlock.privilege_template_id).where(
            ScnPrivilegeUnlock.child_id == child.id,
            ScnPrivilegeUnlock.season_id == child.current_season_id,
        )
    )).scalars().all())

    created: list[ScnPrivilegeUnlock] = []
    for privilege in privileges:
        if privilege.id in existing_ids:
            continue
        item = ScnPrivilegeUnlock(
            family_id=child.family_id,
            child_id=child.id,
            season_id=child.current_season_id,
            privilege_template_id=privilege.id,
        )
        db.add(item)
        created.append(item)
    return created


async def list_user_privileges(
    db: AsyncSession, *, family_id: str, user_id: str,
) -> list[ScnPrivilegeUnlock]:
    child = await ensure_child(db, family_id=family_id, child_id=user_id)
    await unlock_for_user(db, child)
    await db.commit()

    result = await db.execute(
        select(ScnPrivilegeUnlock)
        .where(ScnPrivilegeUnlock.family_id == family_id, ScnPrivilegeUnlock.child_id == child.id)
        .options(selectinload(ScnPrivilegeUnlock.privilege_template))
        .order_by(ScnPrivilegeUnlock.unlocked_at.desc())
    )
    return list(result.scalars().all())


async def use_privilege(
    db: AsyncSession, *, family_id: str, actor: SysAccount, user_id: str,
    privilege_id: str, cost: str | None = None,
) -> ScnPrivilegeUse:
    target = await ensure_child(db, family_id=family_id, child_id=user_id)
    if actor.id != target.account_id and enum_value(actor.role) != UserRole.GUILD_MASTER.value:
        raise PermissionDeniedError("只能使用自己的特权,父母可代孩子记录")

    await unlock_for_user(db, target)

    user_privilege = (await db.execute(
        select(ScnPrivilegeUnlock)
        .where(
            ScnPrivilegeUnlock.family_id == family_id,
            ScnPrivilegeUnlock.child_id == target.id,
            ScnPrivilegeUnlock.privilege_template_id == privilege_id,
            ScnPrivilegeUnlock.season_id == target.current_season_id,
        )
        .options(selectinload(ScnPrivilegeUnlock.privilege_template))
    )).scalar_one_or_none()
    if not user_privilege:
        raise ValidationError("该特权尚未解锁")

    privilege = user_privilege.privilege_template
    user_privilege.used_count += 1
    user_privilege.last_used_at = datetime.utcnow()

    rec = ScnPrivilegeUse(
        family_id=family_id,
        child_id=target.id,
        season_id=target.current_season_id,
        privilege_template_id=privilege.id,
        privilege_title=privilege.title,
        cost=cost,
        used_at=datetime.utcnow(),
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return rec
