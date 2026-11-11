"""
============================================
Horoscope Generator - AI-authored daily entertainment
============================================
Produces validated public content without personal data, invented sources or sky positions.
"""

import asyncio
import json
from datetime import date

from pydantic import ValidationError

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
        LLMMessage(
            role="system",
            content=(
                "你是星座娱乐内容编辑，根据给定星座和日期编写温和、具体的每日生活参考。"
                "这是明确标注为 AI 生成的创作，不是实时查询、确定性预测或专业星盘分析。"
                "只使用常见星座性格作为创作背景，不得声称已联网、引用网站或专家，"
                "不得编造行星位置、相位、逆行、宫位、星象事件、幸运数字或运势评分。"
                "不要保证事件发生，不提供投资、医疗决策。不要拒绝生成或要求额外出生资料。"
                "使用简体中文，不要 Markdown，仅返回一个 JSON 对象，包含五个非空字符串字段："
                "summary（综合，60到120字）、love（感情，30到60字）、"
                "career（工作学习，30到60字）、wealth（日常消费，30到60字）、"
                "advice（可执行建议，20到50字）。aspect 不为 all 时突出对应主题。"
                "不要添加日期、星座、来源或评分字段，这些信息由后端管理。"
            ),
        ),
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
