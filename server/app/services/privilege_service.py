"""特权解锁与使用服务。"""
from __future__ import annotations


from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.models.enums import UserRole
from app.models.scn_privilege_template import ScnPrivilegeTemplate
from app.models.scn_privilege_unlock import ScnPrivilegeUnlock
from app.models.scn_privilege_use import ScnPrivilegeUse
from app.models.sys_account import SysAccount
from app.models.sys_child import SysChild
from app.common.timeutil import utcnow
from app.schemas.privilege import PrivilegeTemplateCreate, PrivilegeTemplateUpdate
from app.services import season_service


def enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


async def ensure_child(db: AsyncSession, *, family_id: str, child_id: str) -> SysChild:
    child = await db.get(SysChild, child_id)
    if child is None:
        child = (
            await db.execute(select(SysChild).where(SysChild.account_id == child_id))
        ).scalar_one_or_none()
    if not child:
        raise NotFoundError(f"孩子 {child_id} 不存在")
    if child.family_id != family_id:
        raise PermissionDeniedError("只能操作自己家庭成员的特权")
    return child


async def unlock_for_user(db: AsyncSession, user: SysChild | SysAccount) -> list[ScnPrivilegeUnlock]:
    """按当前等级补齐孩子已达到等级的特权。"""
    if isinstance(user, SysAccount):
        if enum_value(user.role) != UserRole.ADVENTURER.value:
            return []
        child = (
            await db.execute(select(SysChild).where(SysChild.account_id == user.id))
        ).scalar_one_or_none()
        if child is None:
            return []
    else:
        child = user

    privileges = list((await db.execute(
        select(ScnPrivilegeTemplate).where(
            or_(ScnPrivilegeTemplate.family_id == child.family_id, ScnPrivilegeTemplate.is_system.is_(True)),
            ScnPrivilegeTemplate.level_required <= child.level,
            ScnPrivilegeTemplate.is_active.is_(True),
        )
    )).scalars().all())
    if not privileges:
        return []

    existing_ids = set((await db.execute(
        select(ScnPrivilegeUnlock.privilege_template_id).where(
            ScnPrivilegeUnlock.child_id == child.id,
            ScnPrivilegeUnlock.season_id == child.current_season_id,
        )
    )).scalars().all())

    created: list[ScnPrivilegeUnlock] = []
    for privilege in privileges:
        if privilege.id in existing_ids:
            continue
        item = ScnPrivilegeUnlock(
            family_id=child.family_id,
            child_id=child.id,
            season_id=child.current_season_id,
            privilege_template_id=privilege.id,
        )
        db.add(item)
        created.append(item)
    return created


async def list_user_privileges(
    db: AsyncSession, *, family_id: str, user_id: str,
) -> list[ScnPrivilegeUnlock]:
    child = await ensure_child(db, family_id=family_id, child_id=user_id)
    await unlock_for_user(db, child)
    await db.commit()

    result = await db.execute(
        select(ScnPrivilegeUnlock)
        .where(ScnPrivilegeUnlock.family_id == family_id, ScnPrivilegeUnlock.child_id == child.id)
        .options(selectinload(ScnPrivilegeUnlock.privilege_template))
        .order_by(ScnPrivilegeUnlock.unlocked_at.desc())
    )
    return list(result.scalars().all())


async def use_privilege(
    db: AsyncSession, *, family_id: str, actor: SysAccount, user_id: str,
    privilege_id: str, cost: str | None = None,
) -> ScnPrivilegeUse:
    target = await ensure_child(db, family_id=family_id, child_id=user_id)
    if actor.id != target.account_id and enum_value(actor.role) != UserRole.GUILD_MASTER.value:
        raise PermissionDeniedError("只能使用自己的特权,父母可代孩子记录")

    await unlock_for_user(db, target)

    user_privilege = (await db.execute(
        select(ScnPrivilegeUnlock)
        .where(
            ScnPrivilegeUnlock.family_id == family_id,
            ScnPrivilegeUnlock.child_id == target.id,
            ScnPrivilegeUnlock.privilege_template_id == privilege_id,
            ScnPrivilegeUnlock.season_id == target.current_season_id,
        )
        .options(selectinload(ScnPrivilegeUnlock.privilege_template))
    )).scalar_one_or_none()
    if not user_privilege:
        raise ValidationError("该特权尚未解锁")

    privilege = user_privilege.privilege_template
    user_privilege.used_count += 1
    user_privilege.last_used_at = utcnow()

    rec = ScnPrivilegeUse(
        family_id=family_id,
        child_id=target.id,
        season_id=target.current_season_id,
        privilege_template_id=privilege.id,
        privilege_title=privilege.title,
        cost=cost,
        used_at=utcnow(),
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return rec


async def _get_scoped_template(
    db: AsyncSession, *, template_id: str, family_id: str,
) -> ScnPrivilegeTemplate:
    """取模板并做家庭隔离校验。

    - 不存在 / 属于别的家庭 → 404(不泄露模板是否存在于别的家庭,与赛季同口径);
    - 系统模板(`family_id IS NULL`)对本家庭"可见",不在此拦,交由写操作各自
      判定 `is_system` 保护。
    """
    template = await db.get(ScnPrivilegeTemplate, template_id)
    if template is None:
        raise NotFoundError(f"权益模板 {template_id} 不存在")
    if template.family_id is not None and template.family_id != family_id:
        raise NotFoundError(f"权益模板 {template_id} 不存在")
    return template


async def _require_own_season(db: AsyncSession, *, season_id: str | None, family_id: str) -> None:
    """模板可选关联的"来源赛季"须属于本家庭。

    缺省 / 显式 `null` 表示不关联,放行;传了 id 就复用 `season_service.get_season`
    的家庭口径校验 —— 不存在或属于别的家庭一律 404,既避免 FK 违约落到兜底
    handler 变成 500,也堵住把模板挂到别人家庭赛季上的越权引用。
    """
    if season_id is None:
        return
    await season_service.get_season(db, season_id, family_id=family_id)


async def create_privilege_template(
    db: AsyncSession, *, family_id: str, payload: PrivilegeTemplateCreate,
) -> ScnPrivilegeTemplate:
    """新建家庭级权益模板;恒为 `is_system=False`。"""
    await _require_own_season(db, season_id=payload.season_id, family_id=family_id)
    template = ScnPrivilegeTemplate(
        family_id=family_id,
        season_id=payload.season_id,
        level_required=payload.level_required,
        title=payload.title,
        description=payload.description,
        icon=payload.icon,
        is_system=False,
        is_active=payload.is_active,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


async def update_privilege_template(
    db: AsyncSession, *, template_id: str, family_id: str, payload: PrivilegeTemplateUpdate,
) -> ScnPrivilegeTemplate:
    template = await _get_scoped_template(db, template_id=template_id, family_id=family_id)
    if template.is_system:
        raise PermissionDeniedError("系统权益模板不可修改")

    patch = payload.model_dump(exclude_unset=True)
    # 显式传 null 是"客户端可控输入",不能让它写进 nullable=False 列再触发
    # IntegrityError(→500);这里直接判 422。`season_id` 可空,单独放行以保留
    # "清空来源赛季"的能力。
    for key in ("level_required", "title", "description", "icon", "is_active"):
        if key in patch and patch[key] is None:
            raise ValidationError(f"字段 {key} 不能为空")
    if "season_id" in patch:
        await _require_own_season(db, season_id=patch["season_id"], family_id=family_id)

    for key, value in patch.items():
        setattr(template, key, value)
    await db.commit()
    await db.refresh(template)
    return template


async def delete_privilege_template(
    db: AsyncSession, *, template_id: str, family_id: str,
) -> None:
    """删除家庭级权益模板。

    模板删除会级联删除孩子的解锁记录(`scn_privilege_unlock` CASCADE);历史
    使用记录保留(`scn_privilege_use.privilege_template_id` SET NULL)。
    """
    template = await _get_scoped_template(db, template_id=template_id, family_id=family_id)
    if template.is_system:
        raise PermissionDeniedError("系统权益模板不可删除")
    await db.delete(template)
    await db.commit()
