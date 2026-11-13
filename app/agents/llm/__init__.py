"""
============================================
Agent 模型工厂 - 厂商选择与业务模型配置
============================================
统一创建模型适配器，支持各业务指定模型，密钥仍从后端配置读取。
"""

from app.agents.llm.base import LLMAdapter
from app.agents.llm.qwen import QwenLLM
from app.common.exception import AppException
from app.core.config import settings


def create_llm(*, model: str | None = None, enable_search: bool | None = None) -> LLMAdapter:
    """创建模型适配器，未指定模型时沿用公共 Agent 默认配置。"""
    if settings.AGENT_LLM_PROVIDER == "qwen":
        return QwenLLM(model=model, enable_search=enable_search)
    raise AppException(msg="不支持的 Agent 模型厂商")
