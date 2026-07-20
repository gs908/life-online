"""
OpenAI 协议客户端。

适用于:
- OpenAI (https://api.openai.com/v1)
- DeepSeek (https://api.deepseek.com/v1)
- 通义千问 DashScope 兼容模式 (https://dashscope.aliyuncs.com/compatible-mode/v1)
- 智谱 / 月之暗面 / Ollama / vLLM / 自建网关
- 火山引擎 Ark Coding (https://ark.cn-beijing.volces.com/api/coding)
"""
from __future__ import annotations

import json
import logging

from openai import APIError, AsyncOpenAI, RateLimitError

from app.common.exceptions import ExternalServiceError
from app.common.llm.base import LLMClient
from app.common.llm.types import (
    LLMJsonResponse,
    LLMMessage,
    LLMResponse,
    LLMUsage,
)

log = logging.getLogger(__name__)


class OpenAICompatClient(LLMClient):
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._model = model

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[m.model_dump() for m in messages],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except (APIError, RateLimitError) as e:
            log.exception("llm chat failed: %s", e)
            raise ExternalServiceError(f"LLM 调用失败: {e}") from e

        choice = resp.choices[0] if resp.choices else None
        text = choice.message.content if choice and choice.message else ""
        usage = None
        if resp.usage:
            usage = LLMUsage(
                prompt_tokens=resp.usage.prompt_tokens,
                completion_tokens=resp.usage.completion_tokens,
                total_tokens=resp.usage.total_tokens,
            )
        return LLMResponse(text=text or "", usage=usage, raw=resp.model_dump())

    async def chat_json(
        self,
        messages: list[LLMMessage],
        json_schema: dict | None = None,
        *,
        temperature: float = 0.7,
    ) -> LLMJsonResponse:
        # 在 system / 最后一条 user 中追加格式说明,提高遵循率
        hint = "请严格以合法 JSON 格式返回,不要包含代码块标记或额外解释。"
        if json_schema:
            hint += f" 字段需符合以下 schema:{json.dumps(json_schema, ensure_ascii=False)}"
        augmented = list(messages) + [
            LLMMessage(role="user", content=hint),
        ]
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[m.model_dump() for m in augmented],
                temperature=temperature,
                response_format={"type": "json_object"},
            )
        except (APIError, RateLimitError) as e:
            log.exception("llm chat_json failed: %s", e)
            raise ExternalServiceError(f"LLM 调用失败: {e}") from e

        choice = resp.choices[0] if resp.choices else None
        text = (choice.message.content if choice and choice.message else "") or "{}"
        # 解析,失败时降级
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            log.warning("llm 返回非 JSON,尝试剥离首尾: %s", text[:200])
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                if "\n" in cleaned:
                    cleaned = cleaned.split("\n", 1)[1]
            data = json.loads(cleaned or "{}")
        return LLMJsonResponse(data=data, raw=resp.model_dump())
