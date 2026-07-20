"""
JWT 工具:签发 / 校验 access token 和 refresh token。

access 存内存(前端不持久化),
refresh 通过 HttpOnly cookie 下发(后续接入)。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import jwt

from app.config import settings


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_in: int     # seconds
    refresh_expires_in: int    # seconds


def _now() -> int:
    return int(time.time())


def _encode(payload: dict[str, Any], expires_in: int) -> str:
    payload = {**payload, "iat": _now(), "exp": _now() + expires_in}
    return jwt.encode(payload, settings.jwt.secret, algorithm=settings.jwt.algorithm)


def issue_tokens(user_id: str, *, role: str, extra: dict[str, Any] | None = None) -> TokenPair:
    base = {"sub": str(user_id), "role": role, "type": "access"}
    if extra:
        base.update(extra)
    access = _encode(base, settings.jwt.access_expires_minutes * 60)

    refresh = _encode(
        {"sub": str(user_id), "role": role, "type": "refresh"},
        settings.jwt.refresh_expires_days * 86400,
    )
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        access_expires_in=settings.jwt.access_expires_minutes * 60,
        refresh_expires_in=settings.jwt.refresh_expires_days * 86400,
    )


def decode_token(token: str) -> dict[str, Any]:
    """校验并返回 payload。失败抛 jwt.PyJWTError 子类。"""
    return jwt.decode(
        token,
        settings.jwt.secret,
        algorithms=[settings.jwt.algorithm],
    )
