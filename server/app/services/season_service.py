"""赛季服务。"""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ConflictError, NotFoundError
from app.models.enums import TaskStatus
from app.models.scn_season import ScnSeason
from app.models.scn_task_instance import ScnTaskInstance


async def create_season(db: AsyncSession, *, family_id: str, **kwargs) -> ScnSeason:
    await db.execute(
        update(ScnSeason)
        .where(ScnSeason.family_id == family_id, ScnSeason.is_active.is_(True))
        .values(is_active=False)
    )
    season = ScnSeason(family_id=family_id, **kwargs)
    db.add(season)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("该家庭已存在激活中的赛季,请稍后重试") from exc
    await db.refresh(season)
    return season


async def get_active_season(db: AsyncSession, family_id: str) -> ScnSeason | None:
    result = await db.execute(
        select(ScnSeason)
        .where(ScnSeason.family_id == family_id, ScnSeason.is_active.is_(True))
        .order_by(ScnSeason.id.desc())
    )
    return result.scalar_one_or_none()


async def get_season(db: AsyncSession, season_id: str, *, family_id: str | None = None) -> ScnSeason:
    """按 id 取赛季;传入 family_id 时按家庭校验归属,跨家庭一律视为不存在(404),
    不泄露赛季是否存在于别的家庭(与 family_service.get_adventurer_in_family 一致的约定)。
    """
    s = await db.get(ScnSeason, season_id)
    if not s or (family_id is not None and s.family_id != family_id):
        raise NotFoundError(f"赛季 {season_id} 不存在")
    return s


async def list_seasons(db: AsyncSession, family_id: str) -> list[ScnSeason]:
    result = await db.execute(
        select(ScnSeason)
        .where(ScnSeason.family_id == family_id)
        .order_by(ScnSeason.start_date.desc())
    )
    return list(result.scalars().all())


async def update_season(
    db: AsyncSession, season_id: str, family_id: str | None = None, **patch
) -> ScnSeason:
    s = await get_season(db, season_id, family_id=family_id)
    if patch.get("is_active") is True:
        await db.execute(
            update(ScnSeason)
            .where(ScnSeason.family_id == s.family_id, ScnSeason.is_active.is_(True), ScnSeason.id != s.id)
            .values(is_active=False)
        )
    for k, v in patch.items():
        if v is not None:
            setattr(s, k, v)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("该家庭已存在激活中的赛季,请稍后重试") from exc
    await db.refresh(s)
    return s


async def delete_season(db: AsyncSession, *, season_id: str, family_id: str) -> None:
    s = await get_season(db, season_id, family_id=family_id)
    await db.delete(s)
    await db.commit()


async def activate_season(db: AsyncSession, *, season_id: str, family_id: str) -> ScnSeason:
    return await update_season(db, season_id, family_id=family_id, is_active=True)


async def season_history(db: AsyncSession, family_id: str) -> list[dict]:
    """历史赛季 + 每个赛季的任务统计(供 Web 管理台历史面板展示)。"""
    seasons = await list_seasons(db, family_id)
    out: list[dict] = []
    for s in seasons:
        tasks = (await db.execute(
            select(ScnTaskInstance).where(ScnTaskInstance.season_id == s.id)
        )).scalars().all()
        total = len(tasks)
        completed_tasks = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        out.append({
            "season": s,
            "total_tasks": total,
            "completed_tasks": len(completed_tasks),
            "total_xp": sum(t.xp_awarded or 0 for t in completed_tasks),
        })
    return out
