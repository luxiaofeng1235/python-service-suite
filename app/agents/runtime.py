"""
============================================
Function Calling Runtime - Framework-independent execution
============================================
Runs bounded tool loops and emits internal steps for business services to persist.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel, JsonValue, ValidationError

from app.agents.llm.base import LLMAdapter, LLMMessage, ToolCall, ToolFunction
from app.common.exception import AppException
from app.core.config import settings
from app.pkg.logging import app_logger


@dataclass(frozen=True)
class AgentTool:
    """Bind a validated function schema to a backend business function."""

    name: str
    description: str
    parameters: type[BaseModel]
    handler: Callable[..., Awaitable[JsonValue]]

    def schema(self) -> dict[str, JsonValue]:
        """Export the compatible API function description."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters.model_json_schema(),
            },
        }


@dataclass(frozen=True)
class AgentStep:
    """Represent model and tool lifecycle steps without exposing provider objects."""

    type: Literal[
        "model_start", "delta", "reasoning", "assistant", "tool_start", "tool_end", "done"
    ]
    content: str = ""
    message: LLMMessage | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    success: bool = True
    usage: dict[str, JsonValue] = field(default_factory=dict)


class AgentRunner(Protocol):
    """Allow a future framework runner to preserve the same persistence boundary."""

    name: str

    def run(self, history: list[LLMMessage]) -> AsyncIterator[AgentStep]:
        """Run one user turn and emit application lifecycle steps."""
        ...


class FunctionCallingRunner:
    """Execute native Function Calling with bounded sequential tool invocations."""

    def __init__(
        self,
        name: str,
        system_prompt: str,
        llm: LLMAdapter,
        tools: Sequence[AgentTool],
        *,
        max_tool_rounds: int | None = None,
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.llm = llm
        self.tools = {tool.name: tool for tool in tools}
        if len(self.tools) != len(tools):
            raise ValueError("Agent 工具名称不能重复")
        self.max_tool_rounds = (
            settings.AGENT_MAX_TOOL_ROUNDS if max_tool_rounds is None else max_tool_rounds
        )
        if self.max_tool_rounds < 0:
            raise ValueError("Agent 工具调用轮数不能为负数")

    async def run(self, history: list[LLMMessage]) -> AsyncIterator[AgentStep]:
        """Collect complete tool arguments before validating and executing them."""
        messages = [LLMMessage(role="system", content=self.system_prompt), *history]
        total_usage: dict[str, JsonValue] = {}
        for round_index in range(self.max_tool_rounds + 1):
            yield AgentStep("model_start")
            text: list[str] = []
            fragments: dict[int, dict[str, str]] = {}
            finish_reason = None
            # 最后一轮只允许模型总结，防止工具循环无限运行。
            schemas = (
                [tool.schema() for tool in self.tools.values()]
                if round_index < self.max_tool_rounds
                else []
            )
            stream = self.llm.stream(messages, schemas)
            try:
                async for chunk in stream:
                    if chunk.content:
                        text.append(chunk.content)
                        yield AgentStep("delta", content=chunk.content)
                    if chunk.reasoning:
                        yield AgentStep("reasoning", content=chunk.reasoning)
                    for delta in chunk.tool_calls:
                        if delta.index >= settings.AGENT_MAX_TOOL_CALLS:
                            raise AppException(msg="Agent 单轮工具调用数量超过限制")
                        part = fragments.setdefault(
                            delta.index, {"id": "", "name": "", "arguments": ""}
                        )
                        part["id"] += delta.id
                        part["name"] += delta.name
                        part["arguments"] += delta.arguments
                        if (
                            len(part["arguments"]) > 20000
                            or len(part["id"]) > 128
                            or len(part["name"]) > 64
                        ):
                            raise AppException(msg="Agent 工具调用参数超过限制")
                    if chunk.finish_reason:
                        finish_reason = chunk.finish_reason
                    for key, value in chunk.usage.items():
                        if isinstance(value, int) and not isinstance(value, bool):
                            total_usage[key] = int(total_usage.get(key, 0)) + value
            finally:
                if hasattr(stream, "aclose"):
                    await stream.aclose()

            if finish_reason not in {"stop", "tool_calls"}:
                raise AppException(msg="Agent 回复未正常完成，请重试")
            calls = self._complete_calls(fragments)
            if calls and (finish_reason != "tool_calls" or not schemas):
                raise AppException(msg="Agent 工具调用未正常结束或已超过轮数限制")
            if finish_reason == "tool_calls" and not calls:
                raise AppException(msg="Agent 未返回完整工具调用")
            assistant = LLMMessage(
                role="assistant", content="".join(text) or None, tool_calls=calls or None
            )
            if not calls and not assistant.content:
                raise AppException(msg="Agent 未返回有效回答")
            messages.append(assistant)
            yield AgentStep("assistant", message=assistant)
            if not calls:
                yield AgentStep("done", usage=total_usage)
                return
            for call in calls:
                yield AgentStep("tool_start", tool_name=call.function.name, tool_call_id=call.id)
                result, success = await self._execute(call)
                message = LLMMessage(
                    role="tool",
                    name=call.function.name,
                    tool_call_id=call.id,
                    content=json.dumps(result, ensure_ascii=False, allow_nan=False),
                )
                messages.append(message)
                yield AgentStep(
                    "tool_end",
                    message=message,
                    tool_name=call.function.name,
                    tool_call_id=call.id,
                    success=success,
                )

    @staticmethod
    def _complete_calls(fragments: dict[int, dict[str, str]]) -> list[ToolCall]:
        """Validate tool-call identifiers and function envelopes."""
        try:
            calls = [
                ToolCall(
                    id=part["id"],
                    function=ToolFunction(name=part["name"], arguments=part["arguments"]),
                )
                for _, part in sorted(fragments.items())
            ]
        except ValidationError as exc:
            raise AppException(msg="Agent 工具调用格式不完整") from exc
        if len({call.id for call in calls}) != len(calls):
            raise AppException(msg="Agent 返回了重复的工具调用标识")
        return calls

    async def _execute(self, call: ToolCall) -> tuple[JsonValue, bool]:
        """Run only registered functions with validated arguments and a timeout."""
        tool = self.tools.get(call.function.name)
        if tool is None:
            return {"ok": False, "error": "该工具未开放"}, False
        try:
            parameters = tool.parameters.model_validate_json(call.function.arguments)
            async with asyncio.timeout(settings.AGENT_TOOL_TIMEOUT):
                result = await tool.handler(**parameters.model_dump())
            # 在返回模型前确认工具结果可安全编码为 JSON。
            if len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode()) > 60000:
                return {"ok": False, "error": "工具返回内容过长，请缩小查询范围"}, False
            return result, True
        except ValidationError:
            return {"ok": False, "error": "工具参数格式错误，请根据工具定义修正参数"}, False
        except TimeoutError:
            return {"ok": False, "error": "工具执行超时，请稍后重试"}, False
        except AppException as exc:
            return {"ok": False, "error": exc.msg}, False
        except Exception as exc:
            app_logger.warning(
                "Agent 工具执行失败 tool={} error_type={}", tool.name, type(exc).__name__
            )
            return {"ok": False, "error": "工具执行失败，请稍后重试"}, False
