"""赛季服务。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError, PermissionDeniedError
from app.models.enums import ThemeId
from app.models.season import Season
from app.models.task import Task
from app.models.enums import TaskStatus


async def create_season(db: AsyncSession, *, family_id: str, **kwargs) -> Season:
    # 同一家庭下,新建一个 active 赛季时,把之前的 active 全部置 False
    await db.execute(
        update(Season)
        .where(Season.family_id == family_id, Season.is_active.is_(True))
        .values(is_active=False)
    )
    season = Season(family_id=family_id, **kwargs)
    db.add(season)
    await db.commit()
    await db.refresh(season)
    return season


async def get_active_season(db: AsyncSession, family_id: str) -> Season | None:
    result = await db.execute(
        select(Season)
        .where(Season.family_id == family_id, Season.is_active.is_(True))
        .order_by(Season.id.desc())
    )
    return result.scalar_one_or_none()


async def get_season(db: AsyncSession, season_id: str) -> Season:
    s = await db.get(Season, season_id)
    if not s:
        raise NotFoundError(f"赛季 {season_id} 不存在")
    return s


async def list_seasons(db: AsyncSession, family_id: str) -> list[Season]:
    result = await db.execute(
        select(Season)
        .where(Season.family_id == family_id)
        .order_by(Season.start_date.desc())
    )
    return list(result.scalars().all())


async def update_season(
    db: AsyncSession, season_id: str, family_id: str | None = None, **patch
) -> Season:
    s = await get_season(db, season_id)
    if family_id is not None and s.family_id != family_id:
        raise PermissionDeniedError("只能更新自己家庭的赛季")
    if patch.get("is_active") is True:
        await db.execute(
            update(Season)
            .where(Season.family_id == s.family_id, Season.is_active.is_(True), Season.id != s.id)
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


async def activate_season(db: AsyncSession, *, season_id: str, family_id: str) -> Season:
    return await update_season(db, season_id, family_id=family_id, is_active=True)


async def season_history(db: AsyncSession, family_id: str) -> list[dict]:
    """历史赛季 + 每个赛季的任务统计(供 SeasonHistory 页面)。"""
    seasons = await list_seasons(db, family_id)
    out: list[dict] = []
    for s in seasons:
        tasks = (await db.execute(
            select(Task).where(Task.season_id == s.id)
        )).scalars().all()
        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        out.append({
            "season": s,
            "total_tasks": total,
            "completed_tasks": completed,
        })
    return out
