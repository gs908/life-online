"""账号路由:查看 / 更新自己 / 每日重置。"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import CurrentUser, DBSession, GuildMasterOnly
from app.models.enums import UserRole
from app.models.sys_account import SysAccount
from app.models.sys_child import SysChild
from app.schemas.common import ApiResponse, ok
from app.schemas.user import AdventurerCreate, UserRead, UserUpdate
from app.services import coin_service, family_service

router = APIRouter(prefix="/sys/accounts", tags=["sys-accounts"])


def _role_value(user: SysAccount) -> str:
    return user.role.value if hasattr(user.role, "value") else str(user.role)


async def _child_for_account(db: AsyncSession, account_id: str) -> SysChild | None:
    return (
        await db.execute(select(SysChild).where(SysChild.account_id == account_id))
    ).scalar_one_or_none()


async def _to_read(db: AsyncSession, user: SysAccount) -> UserRead:
    child = await _child_for_account(db, user.id) if _role_value(user) == UserRole.ADVENTURER.value else None
    return UserRead(
        id=user.id,
        family_id=user.family_id,
        role=_role_value(user),
        name=user.name,
        avatar=user.avatar,
        child_id=child.id if child else None,
        level=child.level if child else 1,
        xp=child.xp if child else 0,
        time_coins=child.time_coin_balance if child else 0,
        daily_abandon_count=child.daily_abandon_count if child else 0,
        last_login_date=child.last_login_date if child else None,
        current_season_id=child.current_season_id if child else None,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get("/me", response_model=ApiResponse[UserRead], summary="当前账号(冒险者含每日重置)")
async def get_me(db: DBSession, user: CurrentUser) -> ApiResponse[UserRead]:
    if _role_value(user) == UserRole.ADVENTURER.value:
        child = await _child_for_account(db, user.id)
        today = date.today()
        if child and child.last_login_date != today:
            await coin_service.reset_daily_allowance(db, child, today)
            await db.commit()
            await db.refresh(child)
            await db.refresh(user)
    return ok(await _to_read(db, user))


@router.patch("/me", response_model=ApiResponse[UserRead], summary="更新自己")
async def patch_me(body: UserUpdate, db: DBSession, user: CurrentUser) -> ApiResponse[UserRead]:
    patch = body.model_dump(exclude_unset=True)
    patch.pop("privileges_unlocked", None)

    if "name" in patch and patch["name"] is not None:
        user.name = patch.pop("name")
    if "avatar" in patch and patch["avatar"] is not None:
        user.avatar = patch.pop("avatar")

    child = await _child_for_account(db, user.id) if _role_value(user) == UserRole.ADVENTURER.value else None
    if child:
        if body.name is not None:
            child.display_name = body.name
        if body.avatar is not None:
            child.avatar = body.avatar
        if body.level is not None:
            child.level = body.level
        if body.xp is not None:
            child.xp = body.xp
        if body.time_coins is not None:
            child.time_coin_balance = body.time_coins
        if body.current_season_id is not None:
            child.current_season_id = body.current_season_id

    await db.commit()
    await db.refresh(user)
    if child:
        await db.refresh(child)
    return ok(await _to_read(db, user))


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
    return ok(await _to_read(db, new_user))
