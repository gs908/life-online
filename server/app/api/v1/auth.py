"""认证路由。

- POST /api/v1/auth/wechat/qrcode      H5/PC 扫码登录入口(占位,需 wechat 完整接入)
- GET  /api/v1/auth/wechat/callback     微信开放平台回调(占位)
- POST /api/v1/auth/wechat/jscode       小程序登录(code 换 token + User)
- POST /api/v1/auth/refresh             refresh token 换 access
- POST /api/v1/auth/logout              登出(客户端清内存中的 token)
- GET  /api/v1/auth/me                  当前用户信息
"""
from __future__ import annotations

import json

from fastapi import APIRouter

from app.deps import CurrentUser, DBSession
from app.schemas.common import ApiResponse, ok
from app.schemas.token import RefreshRequest, TokenPair, WechatJscodeRequest
from app.schemas.user import UserRead
from app.services import auth_service, family_service
from app.services import wechat as wechat_svc

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_to_read(user) -> UserRead:
    role_value = user.role.value if hasattr(user.role, "value") else str(user.role)
    return UserRead(
        id=user.id,
        family_id=user.family_id,
        role=role_value,
        name=user.name,
        avatar=user.avatar,
        level=user.level,
        xp=user.xp,
        time_coins=user.time_coins,
        daily_abandon_count=user.daily_abandon_count,
        last_login_date=user.last_login_date,
        privileges_unlocked=json.loads(user.privileges_unlocked) if user.privileges_unlocked else [],
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.post("/wechat/jscode", response_model=ApiResponse[TokenPair], summary="小程序登录(code → token)")
async def login_with_jscode(body: WechatJscodeRequest, db: DBSession) -> ApiResponse[TokenPair]:
    """小程序 wx.login() 拿到 code,后端用 code 换 openid/unionid。"""
    info = await wechat_svc.jscode2session(code=body.code)
    openid = info["openid"]
    unionid = info.get("unionid")

    user = await family_service.find_user_by_openid(db, openid)
    if not user:
        raise wechat_svc.NeedInviteCodeError(
            openid=openid,
            unionid=unionid,
            nickname=body.nickname or "冒险者",
            avatar=body.avatar_url or "⚔️",
        )

    return ok(auth_service.issue_token_pair(user))


@router.post("/refresh", response_model=ApiResponse[TokenPair], summary="refresh token 换 access")
async def refresh(body: RefreshRequest) -> ApiResponse[TokenPair]:
    return ok(auth_service.refresh_access_token(body.refresh_token))


@router.post("/logout", response_model=ApiResponse[dict], summary="登出(客户端清 token 即可,后端仅做日志)")
async def logout(_: CurrentUser) -> ApiResponse[dict]:
    return ok({"ok": True})


@router.get("/me", response_model=ApiResponse[UserRead], summary="当前用户")
async def me(user: CurrentUser) -> ApiResponse[UserRead]:
    return ok(_user_to_read(user))
