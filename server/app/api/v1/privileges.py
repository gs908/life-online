"""特权路由:查询特权模板、已解锁特权与使用记录。"""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app.deps import CurrentUser, DBSession
from app.models.scn_privilege_template import ScnPrivilegeTemplate
from app.schemas.common import ApiResponse, ok
from app.schemas.privilege import PrivilegeRead, UserPrivilegeRead, UserPrivilegeUseRequest
from app.schemas.redemption import RedemptionRead
from app.services import privilege_service

router = APIRouter(prefix="/scn/privileges", tags=["scn-privileges"])


def _to_privilege_read(p) -> PrivilegeRead:
    return PrivilegeRead(
        id=p.id,
        family_id=p.family_id,
        season_id=p.season_id,
        level_required=p.level_required,
        title=p.title,
        description=p.description,
        icon=p.icon,
        is_system=p.is_system,
        is_active=p.is_active,
    )


def _to_user_privilege_read(up) -> UserPrivilegeRead:
    return UserPrivilegeRead(
        id=up.id,
        family_id=up.family_id,
        child_id=up.child_id,
        season_id=up.season_id,
        privilege_template_id=up.privilege_template_id,
        privilege=_to_privilege_read(up.privilege_template),
        unlocked_at=up.unlocked_at,
        used_count=up.used_count,
        last_used_at=up.last_used_at,
        user_id=up.child_id,
    )


def _to_redemption_read(r) -> RedemptionRead:
    return RedemptionRead(
        id=r.id,
        family_id=r.family_id,
        child_id=r.child_id,
        season_id=r.season_id,
        privilege_template_id=r.privilege_template_id,
        privilege_title=r.privilege_title,
        cost=r.cost,
        used_at=r.used_at,
        user_id=r.child_id,
        privilege_id=r.privilege_template_id,
        date=r.used_at,
    )


@router.get("/templates", response_model=ApiResponse[list[PrivilegeRead]], summary="特权模板树")
async def get_tree(db: DBSession, user: CurrentUser) -> ApiResponse[list[PrivilegeRead]]:
    result = await db.execute(
        select(ScnPrivilegeTemplate)
        .where(
            ScnPrivilegeTemplate.is_active.is_(True),
            or_(ScnPrivilegeTemplate.family_id == user.family_id, ScnPrivilegeTemplate.is_system.is_(True)),
        )
        .order_by(ScnPrivilegeTemplate.level_required)
    )
    return ok([_to_privilege_read(p) for p in result.scalars().all()])


@router.get("/unlocks", response_model=ApiResponse[list[UserPrivilegeRead]], summary="用户已解锁特权")
async def list_unlocked(
    db: DBSession,
    user: CurrentUser,
    child_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
) -> ApiResponse[list[UserPrivilegeRead]]:
    rows = await privilege_service.list_user_privileges(
        db,
        family_id=user.family_id,
        user_id=child_id or user_id or user.id,
    )
    return ok([_to_user_privilege_read(row) for row in rows])


@router.post("/uses", response_model=ApiResponse[RedemptionRead], summary="使用一次已解锁特权")
async def use_privilege(
    body: UserPrivilegeUseRequest, db: DBSession, user: CurrentUser,
) -> ApiResponse[RedemptionRead]:
    rec = await privilege_service.use_privilege(
        db,
        family_id=user.family_id,
        actor=user,
        user_id=body.child_id or body.user_id or user.id,
        privilege_id=body.privilege_template_id or body.privilege_id or "",
        cost=body.cost,
    )
    return ok(_to_redemption_read(rec))
