"""认证服务:JWT 签发、refresh 换 access、按 user_id 加载 User。"""
from __future__ import annotations

import json
from typing import Sequence

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import NotFoundError, UnauthorizedError
from app.common.security.jwt import TokenPair, decode_token, issue_tokens
from app.models.user import User
from app.schemas.token import TokenPair as TokenPairSchema


def _encode_privileges(arr: Sequence[int]) -> str:
    return json.dumps(sorted(set(arr)), ensure_ascii=False)


def _decode_privileges(s: str | None) -> list[int]:
    if not s:
        return []
    try:
        v = json.loads(s)
        return [int(x) for x in v if isinstance(x, (int, float))]
    except (ValueError, TypeError):
        return []


def issue_token_pair(user: User) -> TokenPairSchema:
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    pair = issue_tokens(user.id, role=role)
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

    user_id = payload["sub"]
    role = payload.get("role", "ADVENTURER")
    return TokenPairSchema(
        **{  # 借用 issue_tokens 行为但直接构造
            **issue_tokens(user_id, role=role).__dict__,
        }
    )


async def load_user(db: AsyncSession, user_id: str) -> User:
    u = await db.get(User, user_id)
    if not u:
        raise NotFoundError(f"用户 {user_id} 不存在")
    return u
