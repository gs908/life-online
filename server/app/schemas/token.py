"""认证相关 DTO。"""
from __future__ import annotations

from pydantic import BaseModel


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
