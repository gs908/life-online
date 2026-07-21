"""家庭路由:创建、加入、成员查询、邀请码。"""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import CurrentUser, DBSession, GuildMasterOnly
from app.models.enums import UserRole
from app.models.sys_account import SysAccount
from app.models.sys_child import SysChild
from app.schemas.common import ApiResponse, ok
from app.schemas.family import (
    FamilyCreate,
    FamilyInviteCreate,
    FamilyInviteRead,
    FamilyJoinRequest,
    FamilyMembersRead,
    FamilyRead,
)
from app.schemas.user import UserRead
from app.services import family_service

router = APIRouter(prefix="/sys/families", tags=["sys-families"])


def _role_value(user: SysAccount) -> str:
    return user.role.value if hasattr(user.role, "value") else str(user.role)


async def _account_to_read(db: AsyncSession, user: SysAccount) -> UserRead:
    child: SysChild | None = None
    if _role_value(user) == UserRole.ADVENTURER.value:
        child = (
            await db.execute(select(SysChild).where(SysChild.account_id == user.id))
        ).scalar_one_or_none()
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


def _family_to_read(f) -> FamilyRead:
    return FamilyRead(id=f.id, name=f.name, owner_id=f.owner_id, created_at=f.created_at)


def _invite_to_read(inv) -> FamilyInviteRead:
    return FamilyInviteRead(
        id=inv.id, family_id=inv.family_id, code=inv.code,
        role=inv.role, created_by=inv.created_by,
        expires_at=inv.expires_at, used_at=inv.used_at, used_by=inv.used_by,
    )


@router.post("", response_model=ApiResponse[FamilyRead], summary="创建家庭(同时创建第一个 GUILD_MASTER)")
async def create_family(body: FamilyCreate, db: DBSession) -> ApiResponse[FamilyRead]:
    f = await family_service.create_family(db, name=body.name, owner_name=body.owner_name)
    return ok(_family_to_read(f))


@router.get("/me", response_model=ApiResponse[FamilyMembersRead], summary="我的家庭成员")
async def get_my_family(db: DBSession, user: CurrentUser) -> ApiResponse[FamilyMembersRead]:
    f = await family_service.get_family(db, user.family_id)
    members = await family_service.list_family_members(db, user.family_id)
    gms: list[UserRead] = []
    advs: list[UserRead] = []
    for member in members:
        item = await _account_to_read(db, member)
        if _role_value(member) == UserRole.GUILD_MASTER.value:
            gms.append(item)
        elif _role_value(member) == UserRole.ADVENTURER.value:
            advs.append(item)
    return ok(FamilyMembersRead(
        family=_family_to_read(f),
        guild_masters=gms,
        adventurers=advs,
    ))


@router.post("/invites", response_model=ApiResponse[FamilyInviteRead], summary="生成邀请码(父母)")
async def create_invite(
    body: FamilyInviteCreate, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[FamilyInviteRead]:
    inv = await family_service.create_invite(
        db, family_id=user.family_id, role=body.role,
        created_by=user.id, expires_in_hours=body.expires_in_hours,
    )
    return ok(_invite_to_read(inv))


@router.post("/join", response_model=ApiResponse[UserRead], summary="用邀请码加入")
async def join_via_invite(body: FamilyJoinRequest, db: DBSession) -> ApiResponse[UserRead]:
    _, user = await family_service.consume_invite(
        db, code=body.code, nickname=body.nickname,
        avatar=body.avatar, openid=body.openid, unionid=body.unionid,
    )
    return ok(await _account_to_read(db, user))
