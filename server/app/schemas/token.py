"""认证相关 DTO。"""
from __future__ import annotations

from pydantic import BaseModel

from app.models.enums import UserRole


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    access_expires_in: int
    refresh_expires_in: int


class WechatJscodeRequest(BaseModel):
    """小程序登录:用 wx.login() 拿到的 code 换后端 token。"""
    code: str
    nickname: str | None = None
    avatar_url: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class DevLoginRequest(BaseModel):
    """开发期非微信登录:按角色获取(或首次创建)一个固定的开发测试账号。

    不需要传 openid / 邀请码,仅在 `DEV_LOGIN_ENABLED=true` 时可用。
    """
    role: UserRole = UserRole.ADVENTURER
    name: str | None = None
