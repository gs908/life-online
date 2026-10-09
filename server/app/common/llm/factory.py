"""
LLM 客户端工厂。

当前只支持 OpenAI 协议(provider 在 settings 隐含为 openai_compat),
切换 base_url / model / api_key 即可指向任意 OpenAI 兼容服务。
"""
from __future__ import annotations

from functools import lru_cache

from app.common.exceptions import ServiceUnavailableError
from app.common.llm.base import LLMClient
from app.common.llm.openai_compat import OpenAICompatClient
from app.config import settings


@lru_cache
def get_llm_client() -> LLMClient:
    cfg = settings.llm
    if not cfg.is_configured:
        raise ServiceUnavailableError(
            "AI 功能未配置:请设置环境变量 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 后重启服务。"
        )
    return OpenAICompatClient(
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        model=cfg.model,
    )
