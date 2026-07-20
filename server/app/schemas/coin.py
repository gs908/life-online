"""时间币流水 DTO。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import CoinTransactionType


class CoinAdjustRequest(BaseModel):
    user_id: str
    amount: int = Field(..., description="正数增加,负数扣减")
    note: str | None = None


class CoinTransactionRead(BaseModel):
    id: str
    family_id: str
    user_id: str
    task_id: str | None = None
    type: CoinTransactionType
    amount: int
    balance_after: int
    note: str | None = None
    created_at: datetime
