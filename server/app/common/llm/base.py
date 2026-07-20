"""
LLM 客户端抽象接口。

业务层只依赖 LLMClient,不直接 import 具体 provider。
新增 provider(Claude / 本地推理 / ...):实现该接口并在 factory.py 注册。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.common.llm.types import LLMJsonResponse, LLMMessage, LLMResponse


class LLMClient(ABC):
    """所有 LLM provider 实现的统一接口。"""

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """多轮对话,返回文本结果。"""

    @abstractmethod
    async def chat_json(
        self,
        messages: list[LLMMessage],
        json_schema: dict | None = None,
        *,
        temperature: float = 0.7,
    ) -> LLMJsonResponse:
        """结构化 JSON 输出。json_schema 可选,用于 provider 支持时约束字段。"""
