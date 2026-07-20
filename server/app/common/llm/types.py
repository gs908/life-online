"""LLM 数据类型。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant"]


class LLMMessage(BaseModel):
    role: Role
    content: str


class LLMUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class LLMResponse(BaseModel):
    text: str
    usage: LLMUsage | None = None
    raw: dict | None = Field(default=None, exclude=True)


class LLMJsonResponse(BaseModel):
    data: dict
    raw: dict | None = Field(default=None, exclude=True)
