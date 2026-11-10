"""
============================================
Qwen AI Service - upstream streaming client
============================================
Builds Qwen requests for text streams, multimodal SSE and speech synthesis.
"""

import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
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
        payload = {
            "model": config.model,
            "messages": messages,
            "stream": True,
            "enable_search": config.enable_search,
        }
        async with cls._request(payload) as response:
            async for raw_line in response.aiter_lines():
                for event in cls._parse_sse_line(raw_line):
                    yield event

    @classmethod
    @asynccontextmanager
    async def stream_omni(
        cls, messages: list[dict[str, Any]],
    ) -> AsyncIterator[httpx.Response]:
        """Open an Omni stream using backend model and audio settings."""
        payload = {
            "model": settings.QWEN_OMNI_MODEL,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "modalities": ["text", "audio"],
            "audio": {
                "voice": settings.QWEN_OMNI_AUDIO_VOICE,
                "format": settings.QWEN_OMNI_AUDIO_FORMAT,
            },
            # 音频输出使用非思考模式，联网搜索参数不沿用普通文本对话。
            "enable_thinking": False,
        }
        async with cls._request(payload) as response:
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
            if content_type.lower() != "text/event-stream":
                raise AppException(msg="千问多模态服务未返回事件流，请稍后重试")
            yield response

    @classmethod
    async def chattts(cls, text: str) -> dict[str, Any]:
        """Synthesize speech and return the original completed audio response."""
        if not settings.QWEN_TTS_URL:
            raise AppException(msg="QWEN_TTS_URL 未配置")
        payload = {
            "model": settings.QWEN_TTS_MODEL,
            "input": {
                "text": text,
                "voice": settings.QWEN_TTS_VOICE,
                "language_type": settings.QWEN_TTS_LANGUAGE_TYPE,
            },
        }
        async with cls._request(payload, url=settings.QWEN_TTS_URL, stream=False) as response:
            # 一次读取完整 JSON，音频由上游提供地址，不在本地下载或合并。
            await response.aread()
            try:
                data = response.json()
            except ValueError as exc:
                raise AppException(msg="语音服务返回格式错误，请稍后重试") from exc
            if not isinstance(data, dict):
                raise AppException(msg="语音服务返回格式错误，请稍后重试")
            if data.get("code"):
                raise AppException(
                    msg=cls._extract_error_message(response.status_code, response.content)
                )

        output = data.get("output")
        audio = output.get("audio") if isinstance(output, dict) else None
        if (
            not isinstance(audio, dict)
            or not isinstance(audio.get("url"), str)
            or not audio["url"].strip()
            or output.get("finish_reason") != "stop"
        ):
            raise AppException(msg="语音服务未返回生成完成的音频地址，请稍后重试")
        # 保留带签名的完整地址、过期时间和用量，调用方按原始结构读取。
        return data

    @classmethod
    @asynccontextmanager
    async def _request(
        cls,
        payload: dict[str, Any],
        *,
        url: str | None = None,
        stream: bool = True,
    ) -> AsyncIterator[httpx.Response]:
        """Share backend authentication, connection policy and HTTP error checks."""
        if not settings.QWEN_API_KEY:
            raise AppException(msg="QWEN_API_KEY 未配置")
        request_url = settings.QWEN_CHAT_URL if url is None else url
        if not request_url:
            raise AppException(msg="QWEN_CHAT_URL 未配置")

        try:
            async with cls._create_client() as client:
                async with client.stream(
                    "POST",
                    request_url,
                    headers={
                        "Authorization": f"Bearer {settings.QWEN_API_KEY}",
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream" if stream else "application/json",
                    },
                    json=payload,
                ) as response:
                    if response.status_code >= 300:
                        body = await response.aread()
                        raise AppException(
                            msg=cls._extract_error_message(response.status_code, body)
                        )
                    yield response
        except httpx.HTTPError as exc:
            raise AppException(msg="千问服务网络异常，请稍后重试") from exc

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
