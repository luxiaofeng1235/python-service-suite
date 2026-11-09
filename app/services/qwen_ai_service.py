"""
============================================
Qwen AI Service - upstream streaming client
============================================
Builds the Qwen chat-completion request and converts upstream SSE events into text deltas.
"""

import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

import httpx

from app.common.exception import AppException
from app.core.config import settings


@dataclass(frozen=True)
class QwenChatConfig:
    """Resolved settings for one Qwen chat completion."""

    model: str
    system_prompt: str
    enable_search: bool = True


class QwenAIService:
    """Qwen-compatible chat completion client."""

    SYSTEM_PROMPT = (
        "你是一个通用 AI 服务平台的智能助手，请根据用户的问题提供准确、清晰、有帮助的回答。"
        "你可以结合联网搜索回答问题；如果用户输入链接，请说明你无法直接访问链接内容，"
        "并请用户粘贴相关内容。全程使用简体中文回答；如果回答中有数学公式，"
        "请使用双美元符号并换行的 Markdown 格式。"
    )

    @classmethod
    def resolve_config(cls, model_id: int, is_deep_reflection: int = 0) -> QwenChatConfig:
        """Resolve the supported search model and its prompt."""
        if model_id != 1:
            raise AppException(msg="不支持的模型类型")

        if is_deep_reflection not in (0, 1):
            raise AppException(msg="深度思考参数错误")

        model = "qwq-plus" if is_deep_reflection else "qwen-max"
        return QwenChatConfig(
            model=model,
            system_prompt=cls.SYSTEM_PROMPT,
            enable_search=True,
        )

    @classmethod
    async def stream_completion(
        cls,
        messages: list[dict[str, Any]],
        config: QwenChatConfig,
    ) -> AsyncGenerator[tuple[str, str], None]:
        """Yield reasoning and answer deltas from the Qwen SSE response."""
        if not settings.QWEN_API_KEY:
            raise AppException(msg="QWEN_API_KEY 未配置")
        if not settings.QWEN_CHAT_URL:
            raise AppException(msg="QWEN_CHAT_URL 未配置")

        async with cls._create_client() as client:
            async with client.stream(
                "POST",
                settings.QWEN_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {settings.QWEN_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.model,
                    "messages": messages,
                    "stream": True,
                    "enable_search": config.enable_search,
                },
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise AppException(
                        msg=cls._extract_error_message(response.status_code, body)
                    )

                async for raw_line in response.aiter_lines():
                    for event in cls._parse_sse_line(raw_line):
                        yield event

    @staticmethod
    def _create_client() -> httpx.AsyncClient:
        """Create an HTTP client with the chat stream timeout policy."""
        return httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=30.0),
            trust_env=False,
        )

    @classmethod
    def _parse_sse_line(cls, raw_line: str) -> list[tuple[str, str]]:
        """Parse one OpenAI-compatible SSE data line."""
        line = raw_line.strip()
        if not line.startswith("data:"):
            return []

        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            return []

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, dict):
            return []

        error = data.get("error")
        if error:
            if isinstance(error, dict):
                message = error.get("message") or error.get("code")
            else:
                message = str(error)
            raise AppException(msg=message or "上游服务返回错误")

        choices = data.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            return []

        delta = choices[0].get("delta") or {}
        if not isinstance(delta, dict):
            return []

        events: list[tuple[str, str]] = []
        reasoning = delta.get("reasoning_content")
        content = delta.get("content")
        if isinstance(reasoning, str) and reasoning:
            events.append(("reasoning", reasoning))
        elif isinstance(content, str) and content:
            events.append(("delta", content))
        return events

    @staticmethod
    def _extract_error_message(status_code: int, body: bytes) -> str:
        """Extract a useful message from an upstream HTTP error response."""
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return f"上游接口调用失败，HTTP {status_code}"

        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict):
            message = error.get("message") or error.get("code")
            if message:
                return str(message)
        if isinstance(data, dict) and (data.get("message") or data.get("code")):
            return str(data.get("message") or data.get("code"))
        return f"上游接口调用失败，HTTP {status_code}"
