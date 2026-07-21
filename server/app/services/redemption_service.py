"""特权使用记录服务。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError, PermissionDeniedError
from app.models.enums import UserRole
from app.models.scn_privilege_use import ScnPrivilegeUse
from app.models.sys_account import SysAccount
from app.models.sys_child import SysChild


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


async def _ensure_family_child(db: AsyncSession, *, family_id: str, user_id: str) -> SysChild:
    child = await db.get(SysChild, user_id)
    if child is None:
        child = (
            await db.execute(select(SysChild).where(SysChild.account_id == user_id))
        ).scalar_one_or_none()
    if not child:
        raise NotFoundError(f"孩子 {user_id} 不存在")
    if child.family_id != family_id:
        raise PermissionDeniedError("只能操作自己家庭成员的特权记录")
    return child


async def record_redemption(
    db: AsyncSession, *, family_id: str, actor: SysAccount, user_id: str,
    privilege_title: str | None, cost: str | None = None,
) -> ScnPrivilegeUse:
    target = await _ensure_family_child(db, family_id=family_id, user_id=user_id)
    if actor.id != target.account_id and _enum_value(actor.role) != UserRole.GUILD_MASTER.value:
        raise PermissionDeniedError("只能记录自己的特权使用,父母可代孩子记录")
    if not privilege_title:
        from app.common.exceptions import ValidationError
        raise ValidationError("privilege_title 不能为空")

    rec = ScnPrivilegeUse(
        family_id=family_id,
        child_id=target.id,
        season_id=target.current_season_id,
        privilege_template_id=None,
        privilege_title=privilege_title,
        cost=cost,
        used_at=datetime.utcnow(),
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return rec


async def list_redemptions(
    db: AsyncSession, *, family_id: str, user_id: str | None = None,
    offset: int = 0, limit: int | None = None,
) -> tuple[list[ScnPrivilegeUse], int]:
    stmt = select(ScnPrivilegeUse).where(ScnPrivilegeUse.family_id == family_id)
    if user_id is not None:
        child = await _ensure_family_child(db, family_id=family_id, user_id=user_id)
        stmt = stmt.where(ScnPrivilegeUse.child_id == child.id)

    total = int((await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar_one())

    stmt = stmt.order_by(ScnPrivilegeUse.used_at.desc()).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    items = list((await db.execute(stmt)).scalars().all())
    return items, total
