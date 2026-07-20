"""家庭服务:创建家庭、加入、查询成员。"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import ConflictError, NotFoundError
from app.models.enums import InviteRole, UserRole
from app.models.family import Family
from app.models.family_invite import FamilyInvite
from app.models.user import User
from app.models.wechat_account import WechatAccount
from app.models.time_config import TimeConfig


def _gen_invite_code() -> str:
    """生成 8 位易读邀请码(去除 0/O/1/I)。"""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


async def create_family(db: AsyncSession, *, name: str, owner_name: str) -> Family:
    """创建家庭 + 第一个 GUILD_MASTER。"""
    family = Family(name=name)
    db.add(family)
    await db.flush()

    owner = User(
        family_id=family.id,
        role=UserRole.GUILD_MASTER,
        name=owner_name,
        avatar="👑",
        level=99,
        time_coins=9999,
    )
    db.add(owner)
    family.owner_id = None  # 先空,flush 后再设
    await db.flush()
    family.owner_id = owner.id

    # 默认时间币配置
    db.add(TimeConfig(family_id=family.id, default_daily_allowance=100))

    await db.commit()
    await db.refresh(family)
    return family


async def get_family(db: AsyncSession, family_id: str) -> Family:
    f = await db.get(Family, family_id)
    if not f:
        raise NotFoundError(f"家庭 {family_id} 不存在")
    return f


async def list_family_members(db: AsyncSession, family_id: str) -> Sequence[User]:
    result = await db.execute(
        select(User).where(User.family_id == family_id).order_by(User.id)
    )
    return result.scalars().all()


async def create_invite(
    db: AsyncSession,
    *,
    family_id: str,
    role: InviteRole,
    created_by: str,
    expires_in_hours: int = 72,
) -> FamilyInvite:
    code = _gen_invite_code()
    invite = FamilyInvite(
        family_id=family_id,
        code=code,
        role=role,
        created_by=created_by,
        expires_at=datetime.utcnow() + timedelta(hours=expires_in_hours),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return invite


async def create_adventurer(
    db: AsyncSession,
    *,
    family_id: str,
    name: str,
    avatar: str = "⚔️",
    role: UserRole = UserRole.ADVENTURER,
) -> User:
    """父母直接创建孩子/冒险者账户,不绑定微信账号。"""
    user = User(
        family_id=family_id,
        role=role.value if hasattr(role, "value") else str(role),
        name=name,
        avatar=avatar,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def consume_invite(
    db: AsyncSession, *, code: str, nickname: str, avatar: str,
    openid: str, unionid: str | None,
) -> tuple[FamilyInvite, User]:
    """用邀请码加入,自动创建 User + WechatAccount。

    返回 (invite, new_user)。若已使用/过期则抛 ConflictError。
    """
    result = await db.execute(
        select(FamilyInvite)
        .where(FamilyInvite.code == code)
        .with_for_update()
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise NotFoundError(f"邀请码 {code} 不存在")
    if invite.used_at is not None:
        raise ConflictError("邀请码已被使用")
    if invite.expires_at < datetime.utcnow():
        raise ConflictError("邀请码已过期")

    invite_role = invite.role.value if hasattr(invite.role, "value") else str(invite.role)
    user = User(
        family_id=invite.family_id,
        role=invite_role,
        name=nickname,
        avatar=avatar,
    )
    db.add(user)
    await db.flush()

    account = WechatAccount(
        user_id=user.id,
        openid=openid,
        unionid=unionid,
        provider="mp",
        nickname=nickname,
        avatar_url=avatar,
    )
    db.add(account)

    invite.used_at = datetime.utcnow()
    invite.used_by = user.id
    await db.commit()
    await db.refresh(invite)
    await db.refresh(user, attribute_names=["wechat_accounts"])
    return invite, user


async def find_user_by_openid(db: AsyncSession, openid: str) -> User | None:
    """已绑定 openid 的用户查询(用于微信登录时查找或创建用户)。"""
    result = await db.execute(
        select(User)
        .join(WechatAccount, WechatAccount.user_id == User.id)
        .where(WechatAccount.openid == openid)
        .options(selectinload(User.wechat_accounts))
    )
    return result.scalar_one_or_none()
