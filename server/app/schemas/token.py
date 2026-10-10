"""认证相关 DTO。"""
from __future__ import annotations

from pydantic import BaseModel, Field

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


class PasswordLoginRequest(BaseModel):
    """网页端账号密码登录(H5/浏览器)。username 大小写不敏感,存储与比对统一小写。"""
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)


class PasswordRegisterRequest(BaseModel):
    """网页端用邀请码注册并登录:消费邀请码,创建账号 + 密码渠道,直接返回 token。"""
    code: str
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)
    nickname: str | None = Field(default=None, max_length=64)
    avatar: str = Field(default="⚔️", max_length=16)


class PasswordChangeRequest(BaseModel):
    """修改/设置自己的密码。

    - 已有密码渠道:必须带 old_password 且校验通过,username 不可改;
    - 首次设置(如微信注册账号补设网页密码):必须带 username,可省略 old_password。
    """
    new_password: str = Field(min_length=8, max_length=128)
    old_password: str | None = None
    username: str | None = Field(default=None, min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")


class DevLoginRequest(BaseModel):
    """开发期非微信登录:按角色获取(或首次创建)一个固定的开发测试账号。

    不需要传 openid / 邀请码,仅在 `DEV_LOGIN_ENABLED=true` 时可用。
    """
    role: UserRole = UserRole.ADVENTURER
    name: str | None = None
