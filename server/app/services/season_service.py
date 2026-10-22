"""赛季服务。"""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ConflictError, NotFoundError, ValidationError
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


async def season_names(db: AsyncSession, season_ids: Iterable[str | None]) -> dict[str, str]:
    """批量取 `{season_id: name}`(读侧补 `season_name` 用,避免逐条 N+1)。

    DEV-50:模板可跨赛季后,实例/模板列表只靠 `season_id` 分不清属于哪个赛季;
    由后端一并返回名字,不让前端再拉一次赛季列表自己做 map。空集合不发查询。
    """
    ids = {sid for sid in season_ids if sid}
    if not ids:
        return {}
    rows = (
        await db.execute(select(ScnSeason.id, ScnSeason.name).where(ScnSeason.id.in_(ids)))
    ).all()
    return {row[0]: row[1] for row in rows}


async def delete_season(db: AsyncSession, *, season_id: str, family_id: str) -> None:
    """删除赛季。

    DEV-50 资产守卫:该赛季下已有 `COMPLETED/EXPIRED` 实例时**拒绝**(422)。
    删赛季会级联抹掉该赛季全部实例、孩子的照片/视频证据与协作记录
    (`scn_task_instance` / `scn_task_proof` / `scn_task_participant` 都是
    `ON DELETE CASCADE`),不可恢复 —— 与 `task_template_service.delete_template`
    对"成长记录是产品资产"的守卫同口径。

    这条守卫不随 `season_id` 改 `SET NULL` 而失效:模板能保住,但**实例与证据
    仍会被带走**,所以仍然要拦。引导家长走"下线赛季"(PATCH is_active=false)。
    """
    s = await get_season(db, season_id, family_id=family_id)
    historical = (
        await db.execute(
            select(ScnTaskInstance.id)
            .where(
                ScnTaskInstance.season_id == season_id,
                ScnTaskInstance.status.in_((TaskStatus.COMPLETED, TaskStatus.EXPIRED)),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if historical is not None:
        raise ValidationError(
            "该赛季已有已完成/已过期的任务记录(孩子的成长记录与证据),不可删除;"
            "如需结束该赛季请改为「下线赛季」(停用),任务与证据会完整保留"
        )
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
