"""特权 DTO。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PrivilegeRead(BaseModel):
    id: str
    family_id: str | None = None
    season_id: str | None = None
    level_required: int
    title: str
    description: str
    icon: str
    is_system: bool = False
    is_active: bool = True


class PrivilegeTemplateCreate(BaseModel):
    """POST /scn/privileges/templates 请求体:新建家庭级权益模板。

    仅家长(GuildMaster)可调;`family_id` 由服务端取当前用户家庭,不接收
    客户端传入,避免越权写入别人家庭。新建模板恒为 `is_system=False`。
    """

    level_required: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=256)
    icon: str = Field(default="⭐", max_length=16)
    season_id: str | None = None
    is_active: bool = True


class PrivilegeTemplateUpdate(BaseModel):
    """PATCH /scn/privileges/templates/{id} 请求体:全部可选,未提供的字段不变。

    系统模板(is_system=True)在服务层被拒绝(403),前端不应提交。
    """

    level_required: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=256)
    icon: str | None = Field(default=None, max_length=16)
    season_id: str | None = None
    is_active: bool | None = None


class UserPrivilegeUseRequest(BaseModel):
    child_id: str | None = None
    user_id: str | None = None
    privilege_template_id: str | None = None
    privilege_id: str | None = None
    cost: str | None = None


class UserPrivilegeRead(BaseModel):
    id: str
    family_id: str
    child_id: str
    season_id: str | None = None
    privilege_template_id: str
    privilege: PrivilegeRead
    unlocked_at: datetime
    used_count: int
    last_used_at: datetime | None = None

    # 兼容旧前端字段名。
    user_id: str | None = None
