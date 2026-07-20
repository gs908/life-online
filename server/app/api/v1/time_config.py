"""时间币配置路由。"""
from __future__ import annotations

from fastapi import APIRouter

from app.deps import CurrentUser, DBSession, GuildMasterOnly
from app.schemas.common import ApiResponse, ok
from app.schemas.time_config import TimeConfigExceptionRead, TimeConfigRead, TimeConfigUpdate
from app.services import coin_service

router = APIRouter(prefix="/time-config", tags=["time-config"])


def _to_read(tc) -> TimeConfigRead:
    return TimeConfigRead(
        family_id=tc.family_id,
        default_daily_allowance=tc.default_daily_allowance,
        exceptions=[
            TimeConfigExceptionRead(day_of_week=e.day_of_week, coin_amount=e.coin_amount)
            for e in tc.exceptions
        ],
    )


@router.get("/me", response_model=ApiResponse[TimeConfigRead], summary="我的家庭时间币配置")
async def get_my_config(db: DBSession, user: CurrentUser) -> ApiResponse[TimeConfigRead]:
    tc = await coin_service.get_or_create_time_config(db, user.family_id)
    return ok(_to_read(tc))


@router.put("/me", response_model=ApiResponse[TimeConfigRead], summary="更新配置(父母)")
async def update_my_config(
    body: TimeConfigUpdate, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[TimeConfigRead]:
    from app.models.time_config_exception import TimeConfigException
    tc = await coin_service.get_or_create_time_config(db, user.family_id)
    if body.default_daily_allowance is not None:
        tc.default_daily_allowance = body.default_daily_allowance
    if body.exceptions is not None:
        # 简单做法:清空再重建
        for e in list(tc.exceptions):
            await db.delete(e)
        await db.flush()
        for ex in body.exceptions:
            db.add(TimeConfigException(
                time_config_id=tc.id,
                day_of_week=ex.day_of_week,
                coin_amount=ex.coin_amount,
            ))
    await db.commit()
    await db.refresh(tc)
    return ok(_to_read(tc))
