"""认证服务:JWT 签发、refresh 换 access、按 account_id 加载 SysAccount。"""
from __future__ import annotations

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError, UnauthorizedError
from app.common.security.jwt import decode_token, issue_tokens
from app.models.sys_account import SysAccount
from app.schemas.token import TokenPair as TokenPairSchema


def issue_token_pair(account: SysAccount) -> TokenPairSchema:
    role = account.role.value if hasattr(account.role, "value") else str(account.role)
    pair = issue_tokens(account.id, role=role)
    return TokenPairSchema(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        access_expires_in=pair.access_expires_in,
        refresh_expires_in=pair.refresh_expires_in,
    )


def refresh_access_token(refresh_token: str) -> TokenPairSchema:
    """用 refresh token 换新 access(也重新签发 refresh)。"""
    try:
        payload = decode_token(refresh_token)
    except jwt.ExpiredSignatureError as e:
        raise UnauthorizedError("refresh token 已过期,请重新登录") from e
    except jwt.PyJWTError as e:
        raise UnauthorizedError("refresh token 无效") from e

    if payload.get("type") != "refresh":
        raise UnauthorizedError("不是 refresh token")

    account_id = payload["sub"]
    role = payload.get("role", "ADVENTURER")
    return TokenPairSchema(**issue_tokens(account_id, role=role).__dict__)


async def load_user(db: AsyncSession, user_id: str) -> SysAccount:
    account = await db.get(SysAccount, user_id)
    if not account:
        raise NotFoundError(f"账号 {user_id} 不存在")
    return account
