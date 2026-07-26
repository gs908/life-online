"""认证路由。"""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import CurrentUser, DBSession
from app.models.enums import UserRole
from app.models.sys_account import SysAccount
from app.models.sys_child import SysChild
from app.schemas.common import ApiResponse, ok
from app.schemas.token import RefreshRequest, TokenPair, WechatJscodeRequest
from app.schemas.user import UserRead
from app.services import auth_service, family_service
from app.services import wechat as wechat_svc

router = APIRouter(prefix="/sys/auth", tags=["sys-auth"])


def _role_value(user: SysAccount) -> str:
    return user.role.value if hasattr(user.role, "value") else str(user.role)


async def account_to_read(db: AsyncSession, user: SysAccount) -> UserRead:
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
        locale=user.locale,
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


@router.post("/wechat/jscode", response_model=ApiResponse[TokenPair], summary="小程序登录(code → token)")
async def login_with_jscode(body: WechatJscodeRequest, db: DBSession) -> ApiResponse[TokenPair]:
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
async def me(db: DBSession, user: CurrentUser) -> ApiResponse[UserRead]:
    return ok(await account_to_read(db, user))
