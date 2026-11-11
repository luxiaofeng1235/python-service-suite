"""
============================================
SSE 流式响应工具模块
============================================
提供 Server-Sent Events 流式响应支持，用于 AI 对话流式输出。

使用方式：
    async def stream_generator():
        for chunk in response:
            yield chunk

    return EventSourceResponse(stream_generator())
"""

import json
from collections.abc import AsyncGenerator, Mapping

import anyio
from sse_starlette.sse import EventSourceResponse
from starlette.types import Receive, Scope, Send


class _ClosingEventSourceResponse(EventSourceResponse):
    """Close paused business generators on disconnect, send errors and cancellation."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await self.body_iterator.aclose()


class SSEUtil:
    """SSE 流式响应工具类"""

    @staticmethod
    def stream_response(
        generator: AsyncGenerator[str, None],
        event: str = "message",
        headers: Mapping[str, str] | None = None,
    ) -> EventSourceResponse:
        """
        创建 SSE 流式响应

        Args:
            generator: 异步生成器，每次 yield 文本块
            event: SSE 事件类型，默认 "message"
            headers: Optional response header overrides.

        Returns:
            EventSourceResponse 对象

        Example:
            async def text_stream():
                for chunk in ["Hello", " World", "!"]:
                    yield chunk
                    await asyncio.sleep(0.1)

            return SSEUtil.stream_response(text_stream())
        """

        async def close_generator():
            with anyio.CancelScope(shield=True):
                await generator.aclose()

        async def event_generator():
            try:
                async for chunk in generator:
                    yield {
                        "data": chunk,
                    }
            finally:
                # SSE 发送时断开连接，也要关闭暂停在 yield 处的业务生成器。
                await close_generator()

        return _ClosingEventSourceResponse(event_generator(), headers=headers)

    @staticmethod
    def json_stream_response(
        generator: AsyncGenerator[dict, None],
        event: str = "message",
    ) -> EventSourceResponse:
        """
        创建 JSON 格式的 SSE 流式响应

        Args:
            generator: 异步生成器，每次 yield 字典
            event: SSE 事件类型

        Returns:
            EventSourceResponse 对象
        """

        async def close_generator():
            with anyio.CancelScope(shield=True):
                await generator.aclose()

        async def event_generator():
            try:
                async for chunk in generator:
                    yield {
                        "event": event,
                        "data": json.dumps(chunk, ensure_ascii=False),
                    }
            finally:
                await close_generator()

        return _ClosingEventSourceResponse(event_generator())
