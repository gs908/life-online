"""特权使用记录路由。"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DBSession
from app.schemas.common import ApiResponse, PageQuery, PageResult, ok
from app.schemas.redemption import RedemptionCreate, RedemptionRead
from app.services import redemption_service

router = APIRouter(prefix="/scn/privilege-uses", tags=["scn-privilege-uses"])


def _to_read(r) -> RedemptionRead:
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


@router.get("", response_model=ApiResponse[PageResult[RedemptionRead]], summary="家庭使用记录")
async def list_records(
    db: DBSession, user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    child_id: str | None = None,
    user_id: str | None = None,
) -> ApiResponse[PageResult[RedemptionRead]]:
    query = PageQuery(page=page, page_size=page_size)
    items, total = await redemption_service.list_redemptions(
        db, family_id=user.family_id, user_id=child_id or user_id,
        offset=query.offset, limit=query.page_size,
    )
    return ok(PageResult(
        items=[_to_read(r) for r in items],
        total=total,
        page=query.page,
        page_size=query.page_size,
    ))


@router.post("", response_model=ApiResponse[RedemptionRead], summary="记录一次特权使用")
async def create_record(
    body: RedemptionCreate, db: DBSession, user: CurrentUser,
) -> ApiResponse[RedemptionRead]:
    r = await redemption_service.record_redemption(
        db, family_id=user.family_id, actor=user, user_id=body.child_id or body.user_id or user.id,
        privilege_title=body.privilege_title, cost=body.cost,
    )
    return ok(_to_read(r))
