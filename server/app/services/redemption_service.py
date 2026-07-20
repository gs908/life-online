"""特权使用记录服务。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError, PermissionDeniedError
from app.models.enums import UserRole
from app.models.redemption import RedemptionRecord
from app.models.user import User


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


async def _ensure_family_user(db: AsyncSession, *, family_id: str, user_id: str) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(f"用户 {user_id} 不存在")
    if user.family_id != family_id:
        raise PermissionDeniedError("只能操作自己家庭成员的特权记录")
    return user


async def record_redemption(
    db: AsyncSession, *, family_id: str, actor: User, user_id: str,
    privilege_title: str | None, cost: str | None = None,
) -> RedemptionRecord:
    target = await _ensure_family_user(db, family_id=family_id, user_id=user_id)
    if actor.id != target.id and _enum_value(actor.role) != UserRole.GUILD_MASTER.value:
        raise PermissionDeniedError("只能记录自己的特权使用,父母可代孩子记录")
    if not privilege_title:
        from app.common.exceptions import ValidationError
        raise ValidationError("privilege_title 不能为空")

    rec = RedemptionRecord(
        family_id=family_id,
        user_id=target.id,
        privilege_id=None,
        privilege_title=privilege_title,
        cost=cost,
        date=datetime.utcnow(),
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return rec


async def list_redemptions(
    db: AsyncSession, *, family_id: str, user_id: str | None = None,
    offset: int = 0, limit: int | None = None,
) -> tuple[list[RedemptionRecord], int]:
    stmt = select(RedemptionRecord).where(RedemptionRecord.family_id == family_id)
    if user_id is not None:
        await _ensure_family_user(db, family_id=family_id, user_id=user_id)
        stmt = stmt.where(RedemptionRecord.user_id == user_id)

    total = int((await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar_one())

    stmt = stmt.order_by(RedemptionRecord.date.desc()).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    items = list((await db.execute(stmt)).scalars().all())
    return items, total
