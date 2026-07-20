"""家庭路由:创建、加入、成员查询、邀请码。"""
from __future__ import annotations

import json

from fastapi import APIRouter

from app.deps import CurrentUser, DBSession, GuildMasterOnly
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

router = APIRouter(prefix="/families", tags=["families"])


def _user_to_read(u) -> UserRead:
    role_value = u.role.value if hasattr(u.role, "value") else str(u.role)
    return UserRead(
        id=u.id, family_id=u.family_id, role=role_value,
        name=u.name, avatar=u.avatar,
        level=u.level, xp=u.xp, time_coins=u.time_coins,
        daily_abandon_count=u.daily_abandon_count,
        last_login_date=u.last_login_date,
        privileges_unlocked=json.loads(u.privileges_unlocked) if u.privileges_unlocked else [],
        created_at=u.created_at, updated_at=u.updated_at,
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
    gms = [_user_to_read(m) for m in members if (m.role.value if hasattr(m.role, "value") else str(m.role)) == "GUILD_MASTER"]
    advs = [_user_to_read(m) for m in members if (m.role.value if hasattr(m.role, "value") else str(m.role)) == "ADVENTURER"]
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
    return ok(_user_to_read(user))
