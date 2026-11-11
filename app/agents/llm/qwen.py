"""
============================================
Qwen Agent Adapter - Streaming Function Calling
============================================
Reuses the existing Qwen HTTP transport and preserves tool and finish events.
"""

import json
from collections.abc import AsyncIterator

from pydantic import JsonValue

from app.agents.llm.base import LLMChunk, LLMMessage, ToolCallDelta
from app.common.exception import AppException
from app.core.config import settings
from app.services.qwen_ai_service import QwenAIService


class QwenLLM:
    """Adapt Qwen's compatible API to the Agent streaming contract."""

    def __init__(self, model: str | None = None):
        self.model = model or settings.AGENT_MODEL

    async def stream(
        self, messages: list[LLMMessage], tools: list[dict[str, JsonValue]]
    ) -> AsyncIterator[LLMChunk]:
        """Yield validated chunks and close the HTTP response on cancellation."""
        payload = {
            "model": self.model,
            "messages": [message.model_dump(exclude_none=True) for message in messages],
            "stream": True,
            "stream_options": {"include_usage": True},
            # 第一版使用非思考模式执行工具；不沿用普通搜索对话的模型策略。
            "enable_thinking": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
            payload["parallel_tool_calls"] = False

        async with QwenAIService.request(payload) as response:
            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
            if content_type != "text/event-stream":
                raise AppException(msg="Agent 模型未返回事件流")
            data_lines: list[str] = []
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
                elif not line and data_lines:
                    data = "\n".join(data_lines)
                    data_lines.clear()
                    if data == "[DONE]":
                        return
                    yield self._parse_chunk(data)
            if data_lines:
                data = "\n".join(data_lines)
                if data != "[DONE]":
                    yield self._parse_chunk(data)

    @staticmethod
    def _parse_chunk(raw: str) -> LLMChunk:
        """Reject malformed provider data instead of silently truncating output."""
        try:
            data = json.loads(raw)
            if not isinstance(data, dict) or data.get("error"):
                raise ValueError("Invalid chunk")
            usage = data.get("usage") or {}
            choices = data.get("choices") or []
            if not isinstance(usage, dict) or not isinstance(choices, list):
                raise ValueError("Invalid chunk fields")
            if not choices:
                return LLMChunk(usage=usage)
            choice = choices[0]
            delta = choice.get("delta") or {}
            tool_deltas = []
            for call in delta.get("tool_calls") or []:
                function = call.get("function") or {}
                index = call["index"]
                if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                    raise ValueError("Invalid tool index")
                values = (
                    call.get("id") or "",
                    function.get("name") or "",
                    function.get("arguments") or "",
                )
                if not all(isinstance(value, str) for value in values):
                    raise ValueError("Invalid tool fragment")
                tool_deltas.append(ToolCallDelta(index, *values))
            content = delta.get("content") or ""
            reasoning = delta.get("reasoning_content") or ""
            finish_reason = choice.get("finish_reason")
            if not isinstance(content, str) or not isinstance(reasoning, str):
                raise ValueError("Invalid text fragment")
            if finish_reason is not None and not isinstance(finish_reason, str):
                raise ValueError("Invalid finish reason")
            return LLMChunk(content, reasoning, tuple(tool_deltas), finish_reason, usage)
        except (ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
            raise AppException(msg="Agent 模型返回格式错误或服务异常") from exc
