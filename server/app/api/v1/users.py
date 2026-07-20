"""用户路由:查看 / 更新自己 / 每日重置。"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter

from app.deps import CurrentUser, DBSession, GuildMasterOnly
from app.models.enums import UserRole
from app.schemas.common import ApiResponse, ok
from app.schemas.user import AdventurerCreate, UserRead, UserUpdate
from app.services import coin_service, family_service

router = APIRouter(prefix="/users", tags=["users"])


def _to_read(user) -> UserRead:
    role_value = user.role.value if hasattr(user.role, "value") else str(user.role)
    return UserRead(
        id=user.id, family_id=user.family_id, role=role_value,
        name=user.name, avatar=user.avatar,
        level=user.level, xp=user.xp, time_coins=user.time_coins,
        daily_abandon_count=user.daily_abandon_count,
        last_login_date=user.last_login_date,
        privileges_unlocked=json.loads(user.privileges_unlocked) if user.privileges_unlocked else [],
        created_at=user.created_at, updated_at=user.updated_at,
    )


@router.get("/me", response_model=ApiResponse[UserRead], summary="当前用户(含每日重置)")
async def get_me(db: DBSession, user: CurrentUser) -> ApiResponse[UserRead]:
    today = date.today()
    if user.last_login_date != today:
        await coin_service.reset_daily_allowance(db, user, today)
        await db.commit()
        await db.refresh(user)
    return ok(_to_read(user))


@router.patch("/me", response_model=ApiResponse[UserRead], summary="更新自己")
async def patch_me(body: UserUpdate, db: DBSession, user: CurrentUser) -> ApiResponse[UserRead]:
    patch = body.model_dump(exclude_unset=True)
    if "privileges_unlocked" in patch and patch["privileges_unlocked"] is not None:
        user.privileges_unlocked = json.dumps(patch.pop("privileges_unlocked"))
    else:
        patch.pop("privileges_unlocked", None)
    for k, v in patch.items():
        setattr(user, k, v)
    await db.commit()
    await db.refresh(user)
    return ok(_to_read(user))


@router.post("/adventurers", response_model=ApiResponse[UserRead], summary="直接创建孩子冒险者账户(父母)")
async def create_adventurer(
    body: AdventurerCreate, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[UserRead]:
    new_user = await family_service.create_adventurer(
        db,
        family_id=user.family_id,
        name=body.name,
        avatar=body.avatar,
        role=UserRole.ADVENTURER,
    )
    return ok(_to_read(new_user))
