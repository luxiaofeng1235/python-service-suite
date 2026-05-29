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
from collections.abc import AsyncGenerator

from sse_starlette.sse import EventSourceResponse


class SSEUtil:
    """SSE 流式响应工具类"""

    @staticmethod
    def stream_response(
        generator: AsyncGenerator[str, None],
        event: str = "message",
    ) -> EventSourceResponse:
        """
        创建 SSE 流式响应

        Args:
            generator: 异步生成器，每次 yield 文本块
            event: SSE 事件类型，默认 "message"

        Returns:
            EventSourceResponse 对象

        Example:
            async def text_stream():
                for chunk in ["Hello", " World", "!"]:
                    yield chunk
                    await asyncio.sleep(0.1)

            return SSEUtil.stream_response(text_stream())
        """

        async def event_generator():
            async for chunk in generator:
                yield {
                    "data": chunk,
                }

        return EventSourceResponse(event_generator())

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

        async def event_generator():
            async for chunk in generator:
                yield {
                    "event": event,
                    "data": json.dumps(chunk, ensure_ascii=False),
                }

        return EventSourceResponse(event_generator())
