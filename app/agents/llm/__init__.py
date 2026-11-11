"""
============================================
Agent LLM Factory - Provider selection
============================================
Keeps provider selection in the Agent model layer and credentials in backend settings.
"""

from app.agents.llm.base import LLMAdapter
from app.agents.llm.qwen import QwenLLM
from app.common.exception import AppException
from app.core.config import settings


def create_llm(*, enable_search: bool | None = None) -> LLMAdapter:
    """Build the configured Agent model adapter."""
    if settings.AGENT_LLM_PROVIDER == "qwen":
        return QwenLLM(enable_search=enable_search)
    raise AppException(msg="不支持的 Agent 模型厂商")
