"""
============================================
千问公共服务 - SDK 流式请求与原生接口调用
============================================
通过 OpenAI 异步 SDK 接收普通对话和 Agent 分片，转发多模态原始 SSE。
统一读取后端密钥、配置连接策略并处理异常，原生 TTS 和向量接口保留 HTTP 调用。
"""

import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any

import anyio
import httpx
import httpx2
from openai import (
    APIConnectionError,
    APIError,
    APIResponseValidationError,
    APIStatusError,
    AsyncAPIResponse,
    AsyncOpenAI,
    AsyncStream,
    DefaultAsyncHttpxClient,
    Timeout,
)
from openai.types.chat import ChatCompletionChunk

from app.common.exception import AppException
from app.core.config import settings


@dataclass(frozen=True)
class QwenChatConfig:
    """一次普通千问对话使用的模型、提示词和联网开关。"""

    model: str
    system_prompt: str
    enable_search: bool = True


class QwenAIService:
    """集中维护千问兼容接口和原生接口的请求能力。"""

    SYSTEM_PROMPT = (
        "你是一个通用 AI 服务平台的智能助手，请根据用户的问题提供准确、清晰、有帮助的回答。"
        "你可以结合联网搜索回答问题；如果用户输入链接，请说明你无法直接访问链接内容，"
        "并请用户粘贴相关内容。全程使用简体中文回答；如果回答中有数学公式，"
        "请使用双美元符号并换行的 Markdown 格式。"
    )

    @classmethod
    def resolve_config(cls, model_id: int, is_deep_reflection: int = 0) -> QwenChatConfig:
        """根据普通对话参数选择模型，不影响 Agent 的独立模型配置。"""
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
        """从 SDK 分片提取思考与正文，保持普通对话的业务返回格式。"""
        payload = {
            "model": config.model,
            "messages": messages,
            "stream": True,
            "enable_search": config.enable_search,
        }
        async with cls.chat_stream(payload) as stream:
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                reasoning = getattr(delta, "reasoning_content", None)
                if isinstance(reasoning, str) and reasoning:
                    yield "reasoning", reasoning
                if delta.content:
                    yield "delta", delta.content

    @classmethod
    @asynccontextmanager
    async def chat_stream(
        cls,
        payload: dict[str, Any],
    ) -> AsyncIterator[AsyncStream[ChatCompletionChunk]]:
        """由 SDK 拆解上游 SSE，供普通对话及所有 Agent 共用。"""
        async with cls._chat_response(payload) as response:
            async with await response.parse() as stream:
                yield stream

    @classmethod
    @asynccontextmanager
    async def _chat_response(
        cls,
        payload: dict[str, Any],
    ) -> AsyncIterator[AsyncAPIResponse[AsyncStream[ChatCompletionChunk]]]:
        """打开 SDK 流式响应，兼容对象解析与多模态原始字节转发。"""
        stack = AsyncExitStack()
        try:
            client = await stack.enter_async_context(cls._create_sdk_client())
            # 标准选项直接交给 SDK；千问扩展参数通过 extra_body 透传。
            options = {
                key: payload[key]
                for key in (
                    "stream_options",
                    "tools",
                    "tool_choice",
                    "parallel_tool_calls",
                    "modalities",
                    "audio",
                )
                if key in payload
            }
            extra_body = {
                key: value
                for key, value in payload.items()
                if key not in {"model", "messages", "stream", *options}
            }
            response = await stack.enter_async_context(
                client.chat.completions.with_streaming_response.create(
                    model=payload["model"],
                    messages=payload["messages"],
                    stream=True,
                    extra_body=extra_body,
                    extra_headers={"Accept": "text/event-stream"},
                    **options,
                )
            )
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
            if content_type.lower() != "text/event-stream":
                raise AppException(msg="千问服务未返回事件流，请稍后重试")
            yield response
        except APIStatusError as exc:
            body = await exc.response.aread()
            raise AppException(msg=cls._extract_error_message(exc.status_code, body)) from exc
        except (APIConnectionError, httpx2.HTTPError) as exc:
            raise AppException(msg="千问服务网络异常，请稍后重试") from exc
        except (APIResponseValidationError, json.JSONDecodeError) as exc:
            raise AppException(msg="千问服务返回格式错误，请稍后重试") from exc
        except APIError as exc:
            raise AppException(msg="千问流式服务异常，请稍后重试") from exc
        finally:
            # 即使客户端断开或任务被取消，也释放响应及 SDK 的 HTTP 连接。
            with anyio.CancelScope(shield=True):
                await stack.aclose()

    @staticmethod
    def _create_sdk_client() -> AsyncOpenAI:
        """从完整聊天地址派生 SDK 根地址，保持原有超时与无重试策略。"""
        if not settings.QWEN_API_KEY:
            raise AppException(msg="QWEN_API_KEY 未配置")
        url = settings.QWEN_CHAT_URL.rstrip("/")
        if not url:
            raise AppException(msg="QWEN_CHAT_URL 未配置")
        suffix = "/chat/completions"
        if not url.endswith(suffix):
            raise AppException(msg="QWEN_CHAT_URL 必须配置完整的 /chat/completions 接口地址")
        return AsyncOpenAI(
            api_key=settings.QWEN_API_KEY,
            base_url=url[: -len(suffix)],
            timeout=Timeout(300.0, connect=settings.QWEN_CONNECT_TIMEOUT),
            # 禁止 SDK 自动重发请求，避免额外等待和重复生成。
            max_retries=0,
            http_client=DefaultAsyncHttpxClient(trust_env=False),
            _strict_response_validation=True,
        )

    @classmethod
    @asynccontextmanager
    async def stream_omni(
        cls,
        messages: list[dict[str, Any]],
    ) -> AsyncIterator[AsyncAPIResponse[AsyncStream[ChatCompletionChunk]]]:
        """使用 SDK 打开多模态原始 SSE，保留音频、用量及结束标记。"""
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
        async with cls._chat_response(payload) as response:
            yield response

    @classmethod
    async def chattts(cls, text: str) -> dict[str, Any]:
        """调用原生语音合成接口，返回生成完成的音频地址与用量。"""
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
    async def request(
        cls,
        payload: dict[str, Any],
        *,
        url: str | None = None,
        stream: bool = True,
    ) -> AsyncIterator[httpx.Response]:
        """提供原生 HTTP 请求，供向量等非流式接口复用鉴权及异常处理。"""
        async with cls._request(payload, url=url, stream=stream) as response:
            yield response

    @classmethod
    @asynccontextmanager
    async def _request(
        cls,
        payload: dict[str, Any],
        *,
        url: str | None = None,
        stream: bool = True,
    ) -> AsyncIterator[httpx.Response]:
        """统一原生接口的后端鉴权、连接策略和 HTTP 错误检查。"""
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
        """创建原生接口 HTTP 客户端，保持已有连接策略。"""
        return httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=30.0),
            trust_env=False,
        )

    @staticmethod
    def _extract_error_message(status_code: int, body: bytes) -> str:
        """从上游 HTTP 错误响应中提取可读提示。"""
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
