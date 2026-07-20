"""时间币流水路由。"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DBSession, GuildMasterOnly
from app.schemas.coin import CoinAdjustRequest, CoinTransactionRead
from app.schemas.common import ApiResponse, PageQuery, PageResult, ok
from app.services import coin_service

router = APIRouter(prefix="/coins", tags=["coins"])


def _to_read(tx) -> CoinTransactionRead:
    return CoinTransactionRead(
        id=tx.id,
        family_id=tx.family_id,
        user_id=tx.user_id,
        task_id=tx.task_id,
        type=tx.type,
        amount=tx.amount,
        balance_after=tx.balance_after,
        note=tx.note,
        created_at=tx.created_at,
    )


@router.get("/transactions", response_model=ApiResponse[PageResult[CoinTransactionRead]], summary="时间币流水")
async def list_transactions(
    db: DBSession,
    user: CurrentUser,
    user_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> ApiResponse[PageResult[CoinTransactionRead]]:
    query = PageQuery(page=page, page_size=page_size)
    items, total = await coin_service.list_transactions(
        db,
        family_id=user.family_id,
        user_id=user_id,
        offset=query.offset,
        limit=query.page_size,
    )
    return ok(PageResult(
        items=[_to_read(tx) for tx in items],
        total=total,
        page=query.page,
        page_size=query.page_size,
    ))


@router.post("/adjust", response_model=ApiResponse[CoinTransactionRead], summary="人工调整时间币(父母)")
async def adjust_coins(
    body: CoinAdjustRequest, db: DBSession, user: GuildMasterOnly,
) -> ApiResponse[CoinTransactionRead]:
    _, tx = await coin_service.adjust_coins(
        db,
        user_id=body.user_id,
        family_id=user.family_id,
        amount=body.amount,
        note=body.note,
    )
    return ok(_to_read(tx))
