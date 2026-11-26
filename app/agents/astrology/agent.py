"""
============================================
星座智能体定义 - 工具注册与运行器组装
============================================
注册星座档案和运势查询工具，组装 FunctionCallingRunner。
提示词维护在 prompts.py，本文件只负责导入和组装。
"""

from collections.abc import Awaitable, Callable
from zoneinfo import ZoneInfo

from pydantic import JsonValue

from app.agents.astrology.prompts import ASTROLOGY_SYSTEM_PROMPT
from app.agents.llm import create_llm
from app.agents.llm.base import LLMAdapter
from app.agents.runtime import AgentTool, FunctionCallingRunner
from app.core.config import settings
from app.schemas.agent.astrology import EmptyToolRequest, HoroscopeToolRequest
from app.utils.time_ import TimeUtil


def create_astrology_agent(
    profile_handler: Callable[..., Awaitable[JsonValue]],
    horoscope_handler: Callable[..., Awaitable[JsonValue]],
    *,
    llm: LLMAdapter | None = None,
) -> FunctionCallingRunner:
    """Bind trusted backend tools to the astrology Agent."""
    # 每轮提供真实业务日期，避免模型使用训练知识或历史回答猜测“今天”。
    business_now = TimeUtil.get_date().astimezone(ZoneInfo(settings.AGENT_TIMEZONE))
    time_context = (
        f"本轮对话的当前日期为 {business_now.date().isoformat()}，"
        f"业务时区为 {settings.AGENT_TIMEZONE}。"
        "涉及今天、昨天、明天等相对日期时，以此后端时间为准；"
        "历史消息中与本轮时间冲突的日期表述属于过期或错误信息，不得沿用。"
        "工具返回的 current_date 和 timezone 也是后端提供的当前时间依据。"
    )
    return FunctionCallingRunner(
        name="astrology",
        system_prompt=f"{ASTROLOGY_SYSTEM_PROMPT}\n\n{time_context}",
        llm=llm or create_llm(),
        tools=(
            AgentTool(
                "get_user_profile",
                "读取当前登录用户的星座和出生档案，不能指定其他用户。",
                EmptyToolRequest,
                profile_handler,
            ),
            AgentTool(
                "get_horoscope",
                "获取指定星座、日期、领域的运势；优先读缓存，无缓存时生成 AI 娱乐参考。未提供日期则查询今天。",
                HoroscopeToolRequest,
                horoscope_handler,
            ),
        ),
    )
