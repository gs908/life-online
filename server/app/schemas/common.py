"""通用响应 / 分页模型。"""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    data: T | None = None
    msg: str = ""


def ok(data: T | None = None, msg: str = "") -> ApiResponse[T]:
    return ApiResponse(code=0, data=data, msg=msg)


def fail(msg: str, data: T | None = None) -> ApiResponse[T]:
    return ApiResponse(code=1, data=data, msg=msg)


class PageQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
