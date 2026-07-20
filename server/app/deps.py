"""
FastAPI 依赖注入。

- get_settings: 取配置(便于测试时 override)
- get_db: 数据库会话
- get_current_user: 解析 JWT,返回当前 User
- require_role: 角色守卫
"""
from __future__ import annotations

from typing import Annotated, Callable

import jwt
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db.session import get_db as _get_db
from app.common.exceptions import PermissionDeniedError, UnauthorizedError
from app.common.security.jwt import decode_token
from app.config import Settings, get_settings as _get_settings
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth_service import load_user

SettingsDep = Annotated[Settings, Depends(_get_settings)]
DBSession = Annotated[AsyncSession, Depends(_get_db)]


def get_settings() -> Settings:
    return _get_settings()


async def get_db() -> AsyncSession:
    async for s in _get_db():
        yield s


async def _extract_token(authorization: str | None) -> str:
    if not authorization:
        raise UnauthorizedError("缺少 Authorization 头")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise UnauthorizedError("Authorization 头格式错误,期望 'Bearer <token>'")
    return parts[1]


async def get_current_user(
    db: DBSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    token = await _extract_token(authorization)
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError as e:
        raise UnauthorizedError("token 已过期") from e
    except jwt.PyJWTError as e:
        raise UnauthorizedError("token 无效") from e

    if payload.get("type") != "access":
        raise UnauthorizedError("不是 access token")

    user_id = payload["sub"]
    return await load_user(db, user_id)


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: UserRole) -> Callable[[User], User]:
    """依赖工厂:限定某些接口仅特定角色可访问。"""
    async def _checker(user: CurrentUser) -> User:
        role_values = [r.value if isinstance(r, UserRole) else str(r) for r in roles]
        user_role = user.role.value if isinstance(user.role, UserRole) else str(user.role)
        if user_role not in role_values:
            raise PermissionDeniedError(
                f"该接口仅限 {','.join(role_values)} 访问,你是 {user_role}"
            )
        return user
    return _checker


GuildMasterOnly = Annotated[User, Depends(require_role(UserRole.GUILD_MASTER))]
