"""
LLM 客户端工厂。

配置来自 `config.yaml` 的 `ai.llm` 段(经 `require_ai_capability` 统一校验:
未启用 / 未配置时抛 503)。当前只支持 OpenAI 协议,切换 base_url / model /
api_key 即可指向任意 OpenAI 兼容服务;默认请求参数由 yaml 的
`ai.llm.default_params` 收敛,请求级可覆盖。
"""
from __future__ import annotations

from functools import lru_cache

from app.common.ai import require_ai_capability
from app.common.llm.base import LLMClient
from app.common.llm.openai_compat import OpenAICompatClient


@lru_cache
def get_llm_client() -> LLMClient:
    cfg = require_ai_capability("llm")
    params = cfg.default_params
    return OpenAICompatClient(
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        model=cfg.model,
        default_temperature=params.temperature,
        default_max_tokens=params.max_tokens,
        timeout_s=params.timeout_s,
        max_retries=params.max_retries,
    )
