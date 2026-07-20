"""特权解锁与使用服务。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.models.enums import UserRole
from app.models.privilege import Privilege
from app.models.redemption import RedemptionRecord
from app.models.user import User
from app.models.user_privilege import UserPrivilege


def enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


async def unlock_for_user(db: AsyncSession, user: User) -> list[UserPrivilege]:
    """按当前等级补齐用户已达到等级的特权。"""
    if enum_value(user.role) != UserRole.ADVENTURER.value:
        return []

    privileges = list((await db.execute(
        select(Privilege).where(Privilege.level_required <= user.level)
    )).scalars().all())
    if not privileges:
        return []

    existing_ids = set((await db.execute(
        select(UserPrivilege.privilege_id).where(UserPrivilege.user_id == user.id)
    )).scalars().all())

    created: list[UserPrivilege] = []
    for privilege in privileges:
        if privilege.id in existing_ids:
            continue
        item = UserPrivilege(
            family_id=user.family_id,
            user_id=user.id,
            privilege_id=privilege.id,
        )
        db.add(item)
        created.append(item)
    return created


async def list_user_privileges(
    db: AsyncSession, *, family_id: str, user_id: str,
) -> list[UserPrivilege]:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(f"用户 {user_id} 不存在")
    if user.family_id != family_id:
        raise PermissionDeniedError("只能查看自己家庭成员的特权")

    await unlock_for_user(db, user)
    await db.commit()

    result = await db.execute(
        select(UserPrivilege)
        .where(UserPrivilege.family_id == family_id, UserPrivilege.user_id == user_id)
        .order_by(UserPrivilege.unlocked_at.desc())
    )
    return list(result.scalars().all())


async def use_privilege(
    db: AsyncSession, *, family_id: str, actor: User, user_id: str,
    privilege_id: str, cost: str | None = None,
) -> RedemptionRecord:
    target = await db.get(User, user_id)
    if not target:
        raise NotFoundError(f"用户 {user_id} 不存在")
    if target.family_id != family_id:
        raise PermissionDeniedError("只能使用自己家庭成员的特权")
    if actor.id != target.id and enum_value(actor.role) != UserRole.GUILD_MASTER.value:
        raise PermissionDeniedError("只能使用自己的特权,父母可代孩子记录")

    await unlock_for_user(db, target)

    user_privilege = (await db.execute(
        select(UserPrivilege).where(
            UserPrivilege.family_id == family_id,
            UserPrivilege.user_id == target.id,
            UserPrivilege.privilege_id == privilege_id,
        )
    )).scalar_one_or_none()
    if not user_privilege:
        raise ValidationError("该特权尚未解锁")

    privilege = user_privilege.privilege
    user_privilege.used_count += 1
    user_privilege.last_used_at = datetime.utcnow()

    rec = RedemptionRecord(
        family_id=family_id,
        user_id=target.id,
        privilege_id=privilege.id,
        privilege_title=privilege.title,
        cost=cost,
        date=datetime.utcnow(),
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return rec
