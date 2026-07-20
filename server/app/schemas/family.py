"""家庭 / 邀请 DTO。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import InviteRole
from app.schemas.user import UserRead


class FamilyCreate(BaseModel):
    name: str
    owner_name: str = Field(..., description="创建者(首个 GUILD_MASTER)昵称")


class FamilyRead(BaseModel):
    id: str
    name: str
    owner_id: str | None = None
    created_at: datetime


class FamilyInviteCreate(BaseModel):
    role: InviteRole = InviteRole.ADVENTURER
    expires_in_hours: int = Field(default=72, ge=1, le=720)


class FamilyInviteRead(BaseModel):
    id: str
    family_id: str
    code: str
    role: InviteRole
    created_by: str | None = None
    expires_at: datetime
    used_at: datetime | None = None
    used_by: str | None = None


class FamilyJoinRequest(BaseModel):
    """用邀请码加入家庭(扫码后小程序侧调用)。"""
    code: str
    nickname: str
    avatar: str = "⚔️"
    openid: str
    unionid: str | None = None


class FamilyMembersRead(BaseModel):
    family: FamilyRead
    guild_masters: list[UserRead]
    adventurers: list[UserRead]
