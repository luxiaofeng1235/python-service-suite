"""
============================================
星座运势生成器 - AI 创作每日娱乐参考
============================================
生成经过校验的公共内容，不含个人数据、虚构来源或星象位置。
提示词维护在 prompts.py，本文件只负责调用和校验。
"""

import asyncio
import json
from datetime import date

from pydantic import ValidationError

from app.agents.astrology.prompts import HOROSCOPE_GENERATION_PROMPT
from app.agents.llm import create_llm
from app.agents.llm.base import LLMAdapter, LLMMessage
from app.common.exception import AppException
from app.core.config import settings
from app.schemas.agent.astrology import FortuneAspect, GeneratedHoroscope, ZodiacSign

AI_HOROSCOPE_SOURCE = "ai_generated"
AI_HOROSCOPE_NOTICE = "AI 生成的星座运势，仅供娱乐参考。"
MAX_GENERATION_CHARS = 10000


async def generate_horoscope(
    constellation: ZodiacSign,
    fortune_date: date,
    aspect: FortuneAspect,
    *,
    llm: LLMAdapter | None = None,
) -> GeneratedHoroscope:
    """Generate bounded JSON content using the shared model adapter."""
    model = llm or create_llm(enable_search=False)
    messages = [
        LLMMessage(role="system", content=HOROSCOPE_GENERATION_PROMPT),
        LLMMessage(
            role="user",
            content=json.dumps(
                {
                    "constellation": constellation,
                    "fortune_date": fortune_date.isoformat(),
                    "timezone": settings.AGENT_TIMEZONE,
                    "aspect": aspect,
                },
                ensure_ascii=False,
            ),
        ),
    ]
    parts: list[str] = []
    size = 0
    finish_reason = None
    stream = model.stream(messages, [])
    try:
        async with asyncio.timeout(settings.AGENT_TOOL_TIMEOUT):
            async for chunk in stream:
                if chunk.tool_calls:
                    raise AppException(msg="运势生成服务返回异常，请重试")
                size += len(chunk.content)
                if size > MAX_GENERATION_CHARS:
                    raise AppException(msg="运势生成内容过长，请重试")
                parts.append(chunk.content)
                if chunk.finish_reason:
                    finish_reason = chunk.finish_reason
    finally:
        if hasattr(stream, "aclose"):
            await stream.aclose()
    if finish_reason != "stop":
        raise AppException(msg="运势内容未生成完成，请重试")
    content = "".join(parts).strip()
    # 兼容模型额外包裹 JSON 代码块的情况，内容仍需完整通过字段校验。
    if content.startswith("```json\n") and content.endswith("```"):
        content = content[8:-3].strip()
    try:
        return GeneratedHoroscope.model_validate_json(content)
    except ValidationError as exc:
        raise AppException(msg="运势生成格式异常，请重试") from exc
