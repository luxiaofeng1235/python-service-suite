"""
============================================
千问 Agent 适配器 - SDK 分片与工具调用转换
============================================
复用公共 SDK 流式请求，将模型分片转换为独立于厂商的 Agent 数据。
保留正文、思考、工具参数片段、结束原因及用量，不自行解析 SSE。
"""

from collections.abc import AsyncIterator

from openai.types.chat import ChatCompletionChunk
from pydantic import JsonValue

from app.agents.llm.base import LLMChunk, LLMMessage, ToolCallDelta
from app.common.exception import AppException
from app.core.config import settings
from app.services.qwen_ai_service import QwenAIService


class QwenLLM:
    """将千问 SDK 输出适配为公共 Agent 流式协议。"""

    def __init__(self, model: str | None = None, *, enable_search: bool | None = None):
        """读取 Agent 模型和联网开关，允许具体 Agent 覆盖。"""
        self.model = model or settings.AGENT_MODEL
        self.enable_search = (
            settings.AGENT_ENABLE_SEARCH if enable_search is None else enable_search
        )

    async def stream(
        self, messages: list[LLMMessage], tools: list[dict[str, JsonValue]]
    ) -> AsyncIterator[LLMChunk]:
        """接收 SDK 分片；退出或取消时由公共请求服务关闭上游连接。"""
        payload = {
            "model": self.model,
            "messages": [message.model_dump(exclude_none=True) for message in messages],
            "stream": True,
            "stream_options": {"include_usage": True},
            # 星座沿用配置，商品等私域查询可显式关闭联网搜索。
            "enable_search": self.enable_search,
            # 第一版使用非思考模式执行工具；不沿用普通搜索对话的模型策略。
            "enable_thinking": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
            payload["parallel_tool_calls"] = False

        async with QwenAIService.chat_stream(payload) as stream:
            async for chunk in stream:
                yield self._to_llm_chunk(chunk)

    @staticmethod
    def _to_llm_chunk(chunk: ChatCompletionChunk) -> LLMChunk:
        """转换 SDK 对象，保留空 choices 包中的用量及工具参数分片。"""
        try:
            usage = chunk.usage.model_dump(mode="json", exclude_unset=True) if chunk.usage else {}
            if not chunk.choices:
                return LLMChunk(usage=usage)
            choice = chunk.choices[0]
            delta = choice.delta
            tool_deltas = []
            for call in delta.tool_calls or []:
                function = call.function
                index = call.index
                if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                    raise ValueError("工具调用索引无效")
                values = (
                    call.id or "",
                    (function.name or "") if function else "",
                    (function.arguments or "") if function else "",
                )
                if not all(isinstance(value, str) for value in values):
                    raise ValueError("工具调用片段无效")
                tool_deltas.append(ToolCallDelta(index, *values))
            content = delta.content or ""
            reasoning = getattr(delta, "reasoning_content", None) or ""
            finish_reason = choice.finish_reason
            if not isinstance(content, str) or not isinstance(reasoning, str):
                raise ValueError("模型文本片段无效")
            if finish_reason is not None and not isinstance(finish_reason, str):
                raise ValueError("模型结束原因无效")
            return LLMChunk(content, reasoning, tuple(tool_deltas), finish_reason, usage)
        except (ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
            raise AppException(msg="Agent 模型返回格式错误或服务异常") from exc
