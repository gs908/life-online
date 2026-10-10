"""AI 能力段访问与统一降级门槛。

所有 AI 能力(llm / image / video)的调用链路在拿到客户端前必须先过
`require_ai_capability`:未启用 / 未配置时抛 `ServiceUnavailableError`
(503,沿用 DEV-9 的降级约定),错误信息带对应的环境变量名,便于部署排障。
"""
from __future__ import annotations

from typing import Literal

from app.common.exceptions import ServiceUnavailableError
from app.config import AICapabilitySection, settings

CapabilityName = Literal["llm", "image", "video"]


def get_ai_capability(name: CapabilityName) -> AICapabilitySection:
    """按能力名读取配置段。"""
    return getattr(settings.ai, name)


def require_ai_capability(name: CapabilityName) -> AICapabilitySection:
    """校验指定 AI 能力可用,返回其配置段;不可用时抛 503。

    调用方据此只传业务参数,默认参数从返回段的 `default_params` 取。
    """
    cfg = get_ai_capability(name)
    env_prefix = f"AI_{name.upper()}"
    if not cfg.enabled:
        raise ServiceUnavailableError(
            f"AI「{name}」能力未启用:请在 config.yaml 将 ai.{name}.enabled 置为 true "
            f"并配置 {env_prefix}_BASE_URL / {env_prefix}_API_KEY / {env_prefix}_MODEL 后重启服务。"
        )
    if not cfg.is_configured:
        raise ServiceUnavailableError(
            f"AI「{name}」能力未配置:请设置环境变量 "
            f"{env_prefix}_BASE_URL / {env_prefix}_API_KEY / {env_prefix}_MODEL 后重启服务。"
        )
    return cfg
