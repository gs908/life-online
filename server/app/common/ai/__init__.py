"""AI 能力配置访问公共层:按能力(llm/image/video)统一校验与降级。"""
from app.common.ai.capability import CapabilityName, get_ai_capability, require_ai_capability

__all__ = ["CapabilityName", "get_ai_capability", "require_ai_capability"]
