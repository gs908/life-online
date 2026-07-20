"""特权路由:查询特权树、用户解锁特权与使用记录。"""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.deps import CurrentUser, DBSession
from app.models.privilege import Privilege
from app.schemas.common import ApiResponse, ok
from app.schemas.privilege import PrivilegeRead, UserPrivilegeRead, UserPrivilegeUseRequest
from app.schemas.redemption import RedemptionRead
from app.services import privilege_service

router = APIRouter(prefix="/privileges", tags=["privileges"])


def _to_privilege_read(p) -> PrivilegeRead:
    return PrivilegeRead(
        id=p.id, level_required=p.level_required,
        title=p.title, description=p.description, icon=p.icon,
    )


def _to_user_privilege_read(up) -> UserPrivilegeRead:
    return UserPrivilegeRead(
        id=up.id,
        family_id=up.family_id,
        user_id=up.user_id,
        privilege=_to_privilege_read(up.privilege),
        unlocked_at=up.unlocked_at,
        used_count=up.used_count,
        last_used_at=up.last_used_at,
    )


def _to_redemption_read(r) -> RedemptionRead:
    return RedemptionRead(
        id=r.id,
        family_id=r.family_id,
        user_id=r.user_id,
        privilege_id=r.privilege_id,
        privilege_title=r.privilege_title,
        cost=r.cost,
        date=r.date,
    )


@router.get("/tree", response_model=ApiResponse[list[PrivilegeRead]], summary="特权树")
async def get_tree(db: DBSession, _: CurrentUser) -> ApiResponse[list[PrivilegeRead]]:
    result = await db.execute(select(Privilege).order_by(Privilege.level_required))
    return ok([_to_privilege_read(p) for p in result.scalars().all()])


@router.get("/unlocked", response_model=ApiResponse[list[UserPrivilegeRead]], summary="用户已解锁特权")
async def list_unlocked(
    db: DBSession,
    user: CurrentUser,
    user_id: str | None = Query(default=None),
) -> ApiResponse[list[UserPrivilegeRead]]:
    rows = await privilege_service.list_user_privileges(
        db,
        family_id=user.family_id,
        user_id=user_id or user.id,
    )
    return ok([_to_user_privilege_read(row) for row in rows])


@router.post("/use", response_model=ApiResponse[RedemptionRead], summary="使用一次已解锁特权")
async def use_privilege(
    body: UserPrivilegeUseRequest, db: DBSession, user: CurrentUser,
) -> ApiResponse[RedemptionRead]:
    rec = await privilege_service.use_privilege(
        db,
        family_id=user.family_id,
        actor=user,
        user_id=body.user_id,
        privilege_id=body.privilege_id,
        cost=body.cost,
    )
    return ok(_to_redemption_read(rec))
