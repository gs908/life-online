"""时间币流水 DTO。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import CoinTransactionType


class CoinAdjustRequest(BaseModel):
    child_id: str | None = None
    user_id: str | None = None
    amount: int = Field(..., description="正数增加,负数扣减")
    note: str | None = None


class CoinTransactionRead(BaseModel):
    id: str
    family_id: str
    child_id: str
    season_id: str | None = None
    task_instance_id: str | None = None
    type: CoinTransactionType
    amount: int
    balance_after: int
    note: str | None = None
    created_at: datetime

    # 兼容旧前端字段名。
    user_id: str | None = None
    task_id: str | None = None
