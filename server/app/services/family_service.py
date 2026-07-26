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
from app.models.scn_time_config import ScnTimeConfig
from app.models.sys_account import SysAccount
from app.models.sys_channel_wechat import SysChannelWechat
from app.models.sys_child import SysChild
from app.models.sys_family import SysFamily
from app.models.sys_invite import SysInvite
from app.models.sys_parent import SysParent


def _gen_invite_code() -> str:
    """生成 8 位易读邀请码(去除 0/O/1/I)。"""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


async def create_family(db: AsyncSession, *, name: str, owner_name: str) -> SysFamily:
    """创建家庭 + 第一个 GUILD_MASTER。"""
    family = SysFamily(name=name)
    db.add(family)
    await db.flush()

    owner = SysAccount(
        family_id=family.id,
        role=UserRole.GUILD_MASTER,
        name=owner_name,
        avatar="👑",
    )
    db.add(owner)
    await db.flush()

    db.add(SysParent(
        account_id=owner.id,
        family_id=family.id,
        display_name=owner_name,
    ))
    family.owner_id = owner.id

    # 默认时间币配置
    db.add(ScnTimeConfig(family_id=family.id, default_daily_allowance=100))

    await db.commit()
    await db.refresh(family)
    return family


async def get_family(db: AsyncSession, family_id: str) -> SysFamily:
    f = await db.get(SysFamily, family_id)
    if not f:
        raise NotFoundError(f"家庭 {family_id} 不存在")
    return f


async def list_family_members(db: AsyncSession, family_id: str) -> Sequence[SysAccount]:
    result = await db.execute(
        select(SysAccount).where(SysAccount.family_id == family_id).order_by(SysAccount.id)
    )
    return result.scalars().all()


async def create_invite(
    db: AsyncSession,
    *,
    family_id: str,
    role: InviteRole,
    created_by: str,
    expires_in_hours: int = 72,
) -> SysInvite:
    code = _gen_invite_code()
    invite = SysInvite(
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
) -> SysAccount:
    """父母直接创建孩子/冒险者账户,不绑定微信账号。"""
    account = SysAccount(
        family_id=family_id,
        role=role.value if hasattr(role, "value") else str(role),
        name=name,
        avatar=avatar,
    )
    db.add(account)
    await db.flush()
    if (role.value if hasattr(role, "value") else str(role)) == UserRole.ADVENTURER.value:
        db.add(SysChild(
            account_id=account.id,
            family_id=family_id,
            display_name=name,
            avatar=avatar,
        ))
    else:
        db.add(SysParent(
            account_id=account.id,
            family_id=family_id,
            display_name=name,
        ))
    await db.commit()
    await db.refresh(account)
    return account


async def get_adventurer_in_family(
    db: AsyncSession, *, family_id: str, account_id: str
) -> tuple[SysAccount, SysChild]:
    """按家庭 + 账号 id 取孩子账号;跨家庭一律视为不存在(404),不泄露账号是否存在于别的家庭。"""
    account = await db.get(SysAccount, account_id)
    if account is None or account.family_id != family_id:
        raise NotFoundError(f"孩子账号 {account_id} 不存在")
    account_role = account.role.value if hasattr(account.role, "value") else str(account.role)
    if account_role != UserRole.ADVENTURER.value:
        raise NotFoundError(f"孩子账号 {account_id} 不存在")

    child = (
        await db.execute(select(SysChild).where(SysChild.account_id == account_id))
    ).scalar_one_or_none()
    if child is None:
        raise NotFoundError(f"孩子账号 {account_id} 不存在")
    return account, child


async def update_adventurer(
    db: AsyncSession,
    *,
    family_id: str,
    account_id: str,
    name: str | None = None,
    avatar: str | None = None,
) -> tuple[SysAccount, SysChild]:
    """父母更新自己家庭下孩子账号的基础信息(昵称 / 头像),不涉及游戏化数值。"""
    account, child = await get_adventurer_in_family(db, family_id=family_id, account_id=account_id)

    if name is not None:
        account.name = name
        child.display_name = name
    if avatar is not None:
        account.avatar = avatar
        child.avatar = avatar

    await db.commit()
    await db.refresh(account)
    await db.refresh(child)
    return account, child


async def consume_invite(
    db: AsyncSession, *, code: str, nickname: str, avatar: str,
    openid: str, unionid: str | None,
) -> tuple[SysInvite, SysAccount]:
    """用邀请码加入,自动创建 SysAccount + SysChannelWechat。"""
    result = await db.execute(
        select(SysInvite)
        .where(SysInvite.code == code)
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
    account = SysAccount(
        family_id=invite.family_id,
        role=invite_role,
        name=nickname,
        avatar=avatar,
    )
    db.add(account)
    await db.flush()

    if invite_role == UserRole.ADVENTURER.value:
        db.add(SysChild(
            account_id=account.id,
            family_id=invite.family_id,
            display_name=nickname,
            avatar=avatar,
        ))
    else:
        db.add(SysParent(
            account_id=account.id,
            family_id=invite.family_id,
            display_name=nickname,
        ))

    channel = SysChannelWechat(
        account_id=account.id,
        openid=openid,
        unionid=unionid,
        provider="mp",
        nickname=nickname,
        avatar_url=avatar,
    )
    db.add(channel)

    invite.used_at = datetime.utcnow()
    invite.used_by = account.id
    await db.commit()
    await db.refresh(invite)
    await db.refresh(account, attribute_names=["channel_wechats"])
    return invite, account


async def find_user_by_openid(db: AsyncSession, openid: str) -> SysAccount | None:
    """已绑定 openid 的账号查询(用于微信登录时查找或创建账号)。"""
    result = await db.execute(
        select(SysAccount)
        .join(SysChannelWechat, SysChannelWechat.account_id == SysAccount.id)
        .where(SysChannelWechat.openid == openid)
        .options(selectinload(SysAccount.channel_wechats))
    )
    return result.scalar_one_or_none()
