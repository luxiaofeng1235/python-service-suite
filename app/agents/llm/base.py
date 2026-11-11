"""
============================================
Agent LLM Contracts - Provider-independent messages and chunks
============================================
Defines a small streaming boundary for native and future framework adapters.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class ToolFunction(BaseModel):
    """Preserve the provider's function name and serialized arguments."""

    name: str = Field(..., min_length=1, max_length=64, description="Function name")
    arguments: str = Field(..., max_length=20000, description="JSON-encoded function arguments")


class ToolCall(BaseModel):
    """Identify one complete function call."""

    id: str = Field(..., min_length=1, max_length=128, description="Tool call ID")
    type: Literal["function"] = Field("function", description="Tool type")
    function: ToolFunction = Field(..., description="Function and arguments")


class LLMMessage(BaseModel):
    """Represent replayable model messages without framework-specific objects."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant", "tool"] = Field(..., description="Message role")
    content: str | None = Field(None, description="Raw text content")
    tool_calls: list[ToolCall] | None = Field(None, description="Assistant function calls")
    tool_call_id: str | None = Field(None, description="Tool result correlation ID")
    name: str | None = Field(None, description="Tool name")


@dataclass(frozen=True)
class ToolCallDelta:
    """Carry a fragment belonging to a tool call index."""

    index: int
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass(frozen=True)
class LLMChunk:
    """Carry text, tool fragments, termination and usage from one model chunk."""

    content: str = ""
    reasoning: str = ""
    tool_calls: tuple[ToolCallDelta, ...] = ()
    finish_reason: str | None = None
    usage: dict[str, JsonValue] = field(default_factory=dict)


class LLMAdapter(Protocol):
    """Stream model output using the application's message contract."""

    def stream(
        self, messages: list[LLMMessage], tools: list[dict[str, JsonValue]]
    ) -> AsyncIterator[LLMChunk]:
        """Open a model turn; the consumer owns cancellation and persistence."""
        ...
