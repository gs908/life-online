"""
账号密码登录服务(网页端 H5 生产通道,DEV-22)。

- 凭据存 sys_channel_password(与 sys_channel_wechat 并列的渠道表,一账号一条)
- username 统一小写存储/比对,大小写不敏感,全表唯一
- 登录失败限流:进程内滑动窗口计数(同一 username 窗口内失败 N 次即锁),
  不依赖 Redis(当前栈未接入);重启清零,多 worker 部署时各进程独立计数 —— 限流阈值
  视为近似值,接入 Redis 后可升级为精确全局计数
- 复用 auth_service.issue_token_pair 签发标准 JWT token pair
"""
from __future__ import annotations

import threading
import time
from collections import deque

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import ConflictError, RateLimitError, UnauthorizedError
from app.common.security.password import hash_password, verify_password
from app.models.sys_account import SysAccount
from app.models.sys_channel_password import SysChannelPassword
from app.services import family_service


def normalize_username(username: str) -> str:
    """统一小写,实现大小写不敏感的用户名。"""
    return username.strip().lower()


class _LoginThrottle:
    """进程内滑动窗口失败计数器(username -> 最近失败时刻列表)。

    字典容量上限(DEV-26):历史上 key 仅在该用户名登录成功时清除,海量不存在
    用户名喷射会让 key 数量无界增长。达到上限后先清扫窗口外条目,仍满则丢弃
    任意一个条目兜底——攻击者顶多让计数变稀疏(限流偏松),不会撑爆内存。
    接入 Redis 全局限流后本类整体退役。
    """

    # 进程内计数的合理上限:1 万个用户名 × 每个一串时间戳,内存不过几百 KB。
    MAX_KEYS = 10_000

    def __init__(self) -> None:
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, window_s: float, now: float) -> deque[float]:
        dq = self._failures.setdefault(key, deque())
        while dq and dq[0] <= now - window_s:
            dq.popleft()
        return dq

    def _sweep(self, window_s: float, now: float) -> None:
        """清掉所有窗口外(空)条目。窗口取当前调用的 window_s——实践中全局统一,够用。"""
        for key in [k for k, dq in self._failures.items() if not self._prune(k, window_s, now)]:
            del self._failures[key]

    def check(self, key: str, *, max_attempts: int, window_s: float) -> None:
        """超限即抛 429;通过不产生任何副作用。"""
        with self._lock:
            dq = self._prune(key, window_s, time.monotonic())
            if len(dq) >= max_attempts:
                raise RateLimitError(
                    f"登录失败次数过多,请 {int(window_s // 60)} 分钟后再试"
                )

    def record_failure(self, key: str, *, window_s: float) -> None:
        with self._lock:
            now = time.monotonic()
            if key not in self._failures and len(self._failures) >= self.MAX_KEYS:
                self._sweep(window_s, now)
                if len(self._failures) >= self.MAX_KEYS:
                    self._failures.popitem()
            self._prune(key, window_s, now).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


_throttle = _LoginThrottle()

# 时序防枚举(DEV-26):用户不存在时也对固定 dummy 哈希做一次等参数 scrypt verify,
# 使该路径与"密码错误"路径(约 100ms)无可测时间差。惰性生成避免拖慢模块 import;
# 值只会被写入一次,并发下重复计算是良性的。
_dummy_hash: str | None = None


def _timing_equalizer_hash() -> str:
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("timing-equalizer-dummy")
    return _dummy_hash


async def _find_channel_with_account(
    db: AsyncSession, username: str
) -> SysChannelPassword | None:
    result = await db.execute(
        select(SysChannelPassword)
        .where(SysChannelPassword.username == username)
        .options(selectinload(SysChannelPassword.account))
    )
    return result.scalar_one_or_none()


async def login(
    db: AsyncSession,
    *,
    username: str,
    password: str,
    max_attempts: int,
    window_minutes: int,
) -> SysAccount:
    """用户名 + 密码校验;失败统一返回 401(不区分用户不存在/密码错,防用户名枚举)。"""
    key = f"login:{normalize_username(username)}"
    _throttle.check(key, max_attempts=max_attempts, window_s=window_minutes * 60)

    channel = await _find_channel_with_account(db, normalize_username(username))
    if channel is None:
        # 用户不存在也要走一次等参数 scrypt(约 100ms),消除与密码错误路径的时间差
        verify_password(password, _timing_equalizer_hash())
        _throttle.record_failure(key, window_s=window_minutes * 60)
        raise UnauthorizedError("用户名或密码错误")
    if not verify_password(password, channel.password_hash):
        _throttle.record_failure(key, window_s=window_minutes * 60)
        raise UnauthorizedError("用户名或密码错误")

    if channel.account.status != "active":
        raise UnauthorizedError("账号已停用")

    _throttle.reset(key)
    return channel.account


async def register_with_invite(
    db: AsyncSession,
    *,
    code: str,
    username: str,
    password: str,
    nickname: str | None,
    avatar: str = "⚔️",
) -> SysAccount:
    """用邀请码注册网页端账号:消费邀请码 + 创建账号 + 绑定密码渠道。"""
    normalized = normalize_username(username)
    existing = await _find_channel_with_account(db, normalized)
    if existing is not None:
        raise ConflictError("用户名已被使用")

    _, account = await family_service.consume_invite_to_account(
        db, code=code, nickname=nickname or username, avatar=avatar
    )
    db.add(SysChannelPassword(
        account_id=account.id,
        username=normalized,
        password_hash=hash_password(password),
    ))
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ConflictError("用户名已被使用") from e
    await db.refresh(account, attribute_names=["channel_password"])
    return account


async def change_password(
    db: AsyncSession,
    *,
    account: SysAccount,
    username: str | None,
    old_password: str | None,
    new_password: str,
    max_attempts: int,
    window_minutes: int,
) -> None:
    """修改/设置自己的登录密码。

    - 已有密码渠道:必须校验 old_password,同样受失败限流保护(防在线爆破);
    - 首次设置:username 必填(作为网页登录用户名,全表唯一)。
    """
    result = await db.execute(
        select(SysChannelPassword).where(SysChannelPassword.account_id == account.id)
    )
    channel = result.scalar_one_or_none()

    if channel is not None:
        key = f"login:{channel.username}"
        _throttle.check(key, max_attempts=max_attempts, window_s=window_minutes * 60)
        if not old_password or not verify_password(old_password, channel.password_hash):
            _throttle.record_failure(key, window_s=window_minutes * 60)
            raise UnauthorizedError("原密码错误")
        _throttle.reset(key)
        channel.password_hash = hash_password(new_password)
    else:
        if not username:
            raise ConflictError("首次设置密码需要提供 username")
        normalized = normalize_username(username)
        if await _find_channel_with_account(db, normalized) is not None:
            raise ConflictError("该用户名已被使用")
        db.add(SysChannelPassword(
            account_id=account.id,
            username=normalized,
            password_hash=hash_password(new_password),
        ))

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ConflictError("该用户名已被使用") from e
