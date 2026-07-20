"""赛季路由。"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DBSession, GuildMasterOnly
from app.schemas.common import ApiResponse, ok
from app.schemas.season import SeasonCreate, SeasonHistoryItem, SeasonRead, SeasonUpdate
from app.services import season_service

router = APIRouter(prefix="/seasons", tags=["seasons"])


def _to_read(s) -> SeasonRead:
    return SeasonRead(
        id=s.id, family_id=s.family_id, name=s.name, theme_id=s.theme_id,
        narrative_context=s.narrative_context, start_date=s.start_date,
        end_date=s.end_date, is_active=s.is_active,
        created_at=s.created_at, updated_at=s.updated_at,
    )


@router.get("", response_model=ApiResponse[list[SeasonRead]], summary="赛季列表(按家庭)")
async def list_seasons(
    db: DBSession, user: CurrentUser, include_inactive: bool = Query(default=True),
) -> ApiResponse[list[SeasonRead]]:
    seasons = await season_service.list_seasons(db, user.family_id)
    if not include_inactive:
        seasons = [s for s in seasons if s.is_active]
    return ok([_to_read(s) for s in seasons])


@router.get("/active", response_model=ApiResponse[SeasonRead | None], summary="当前激活赛季")
async def get_active(db: DBSession, user: CurrentUser) -> ApiResponse[SeasonRead | None]:
    s = await season_service.get_active_season(db, user.family_id)
    return ok(_to_read(s) if s else None)


@router.get("/history", response_model=ApiResponse[list[SeasonHistoryItem]], summary="赛季历史统计")
async def get_history(db: DBSession, user: CurrentUser) -> ApiResponse[list[SeasonHistoryItem]]:
    rows = await season_service.season_history(db, user.family_id)
    return ok([
        SeasonHistoryItem(
            season=_to_read(row["season"]),
            total_tasks=row["total_tasks"],
            completed_tasks=row["completed_tasks"],
        )
        for row in rows
    ])


@router.get("/{season_id}", response_model=ApiResponse[SeasonRead], summary="赛季详情")
async def get_season(season_id: str, db: DBSession, user: CurrentUser) -> ApiResponse[SeasonRead]:
    s = await season_service.get_season(db, season_id)
    if s.family_id != user.family_id:
        from app.common.exceptions import PermissionDeniedError
        raise PermissionDeniedError("只能查看自己家庭的赛季")
    return ok(_to_read(s))


@router.post("", response_model=ApiResponse[SeasonRead], summary="创建赛季(父母)")
async def create_season(
    body: SeasonCreate, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[SeasonRead]:
    s = await season_service.create_season(
        db, family_id=user.family_id,
        name=body.name, theme_id=body.theme_id, narrative_context=body.narrative_context,
        start_date=body.start_date, end_date=body.end_date,
    )
    return ok(_to_read(s))


@router.patch("/{season_id}", response_model=ApiResponse[SeasonRead], summary="更新赛季(父母)")
async def update_season(
    season_id: str, body: SeasonUpdate, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[SeasonRead]:
    s = await season_service.update_season(
        db, season_id, family_id=user.family_id,
        name=body.name, theme_id=body.theme_id, narrative_context=body.narrative_context,
        end_date=body.end_date, is_active=body.is_active,
    )
    return ok(_to_read(s))


@router.post("/{season_id}/activate", response_model=ApiResponse[SeasonRead], summary="激活赛季(父母)")
async def activate_season(
    season_id: str, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[SeasonRead]:
    s = await season_service.activate_season(db, season_id=season_id, family_id=user.family_id)
    return ok(_to_read(s))


@router.delete("/{season_id}", response_model=ApiResponse[dict], summary="删除赛季(父母)")
async def delete_season(
    season_id: str, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[dict]:
    await season_service.delete_season(db, season_id=season_id, family_id=user.family_id)
    return ok({"deleted": True})
