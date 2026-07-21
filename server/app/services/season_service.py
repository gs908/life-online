"""赛季服务。"""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError, PermissionDeniedError
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
    await db.commit()
    await db.refresh(season)
    return season


async def get_active_season(db: AsyncSession, family_id: str) -> ScnSeason | None:
    result = await db.execute(
        select(ScnSeason)
        .where(ScnSeason.family_id == family_id, ScnSeason.is_active.is_(True))
        .order_by(ScnSeason.id.desc())
    )
    return result.scalar_one_or_none()


async def get_season(db: AsyncSession, season_id: str) -> ScnSeason:
    s = await db.get(ScnSeason, season_id)
    if not s:
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
    s = await get_season(db, season_id)
    if family_id is not None and s.family_id != family_id:
        raise PermissionDeniedError("只能更新自己家庭的赛季")
    if patch.get("is_active") is True:
        await db.execute(
            update(ScnSeason)
            .where(ScnSeason.family_id == s.family_id, ScnSeason.is_active.is_(True), ScnSeason.id != s.id)
            .values(is_active=False)
        )
    for k, v in patch.items():
        if v is not None:
            setattr(s, k, v)
    await db.commit()
    await db.refresh(s)
    return s


async def delete_season(db: AsyncSession, *, season_id: str, family_id: str) -> None:
    s = await get_season(db, season_id)
    if s.family_id != family_id:
        raise PermissionDeniedError("只能删除自己家庭的赛季")
    await db.delete(s)
    await db.commit()


async def activate_season(db: AsyncSession, *, season_id: str, family_id: str) -> ScnSeason:
    return await update_season(db, season_id, family_id=family_id, is_active=True)


async def season_history(db: AsyncSession, family_id: str) -> list[dict]:
    """历史赛季 + 每个赛季的任务统计。"""
    seasons = await list_seasons(db, family_id)
    out: list[dict] = []
    for s in seasons:
        tasks = (await db.execute(
            select(ScnTaskInstance).where(ScnTaskInstance.season_id == s.id)
        )).scalars().all()
        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        out.append({"season": s, "total_tasks": total, "completed_tasks": completed})
    return out
