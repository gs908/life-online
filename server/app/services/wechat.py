"""
微信开放平台 API 封装。

- jscode2session: 小程序 code → openid/unionid
- 扫码登录(qrcode/callback): 暂留接口,需要 OPEN_APPID/SECRET 真实申请后可用
"""
from __future__ import annotations

import logging

import httpx

from app.common.exceptions import AppError, ExternalServiceError, ValidationError
from app.config import settings

log = logging.getLogger(__name__)

JSCODE_URL = "https://api.weixin.qq.com/sns/jscode2session"
OAUTH_TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"
OAUTH_USERINFO_URL = "https://api.weixin.qq.com/sns/userinfo"


class NeedInviteCodeError(AppError):
    """用户未绑定家庭,需要先 join。"""

    code = "need_invite_code"
    http_status = 409

    def __init__(self, *, openid: str, unionid: str | None, nickname: str, avatar: str) -> None:
        self.openid = openid
        self.unionid = unionid
        self.nickname = nickname
        self.avatar = avatar
        super().__init__(
            "用户未关联家庭,需要通过邀请码加入",
            http_status=self.http_status,
        )


async def jscode2session(*, code: str) -> dict:
    """用小程序 code 换 openid / session_key / unionid。"""
    cfg = settings.wechat
    if not cfg.mp_appid or not cfg.mp_secret:
        raise ValidationError("微信小程序未配置 WECHAT_MP_APPID / WECHAT_MP_SECRET")
    params = {
        "appid": cfg.mp_appid,
        "secret": cfg.mp_secret,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(JSCODE_URL, params=params)
        except httpx.HTTPError as e:
            raise ExternalServiceError(f"微信 jscode2session 请求失败: {e}") from e
    data = r.json()
    if "openid" not in data:
        log.error("jscode2session error: %s", data)
        raise ExternalServiceError(f"微信 jscode2session 失败: {data.get('errmsg', data)}")
    return data


def build_qrcode_url(state: str) -> str:
    """拼接微信开放平台扫码登录 URL(H5/PC 用)。"""
    cfg = settings.wechat
    if not cfg.open_appid:
        raise ValidationError("微信开放平台未配置 WECHAT_OPEN_APPID")
    from urllib.parse import urlencode
    return (
        "https://open.weixin.qq.com/connect/qrconnect?"
        + urlencode({
            "appid": cfg.open_appid,
            "redirect_uri": cfg.open_redirect_uri,
            "response_type": "code",
            "scope": "snsapi_login",
            "state": state,
        })
        + "#wechat_redirect"
    )


async def exchange_open_code(*, code: str) -> dict:
    """扫码后:用 code 换 access_token + openid。"""
    cfg = settings.wechat
    params = {
        "appid": cfg.open_appid,
        "secret": cfg.open_secret,
        "code": code,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(OAUTH_TOKEN_URL, params=params)
        except httpx.HTTPError as e:
            raise ExternalServiceError(f"微信 access_token 请求失败: {e}") from e
    data = r.json()
    if "access_token" not in data:
        raise ExternalServiceError(f"微信 access_token 失败: {data.get('errmsg', data)}")
    return data


async def fetch_open_userinfo(*, access_token: str, openid: str) -> dict:
    """拉取扫码用户基本信息。"""
    params = {"access_token": access_token, "openid": openid}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(OAUTH_USERINFO_URL, params=params)
        except httpx.HTTPError as e:
            raise ExternalServiceError(f"微信 userinfo 请求失败: {e}") from e
    data = r.json()
    if "openid" not in data:
        raise ExternalServiceError(f"微信 userinfo 失败: {data.get('errmsg', data)}")
    return data
