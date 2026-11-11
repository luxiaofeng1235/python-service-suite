"""
============================================
Agent Chat Schemas - Requests and stream events
============================================
Keeps the application contract independent of model providers and Agent frameworks.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class AgentChatRequest(BaseModel):
    """Accept one user message and an optional existing session."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=4000, description="User message")
    session_id: UUID | None = Field(
        None, description="Existing session UUID; null creates a session"
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        """Reject whitespace-only messages while preserving their original text."""
        if not value.strip():
            raise ValueError("消息内容不能为空")
        return value


class AgentStreamEvent(BaseModel):
    """Expose stable stream events to future HTTP controllers."""

    type: Literal["session", "delta", "reasoning", "tool_start", "tool_end", "done", "error"] = (
        Field(..., description="Stream event type")
    )
    session_id: str = Field(..., description="Session UUID")
    agent: str = Field(..., description="Agent identifier")
    message_id: int | None = Field(None, description="Persisted message ID")
    content: str | None = Field(None, description="Text delta or user-facing status")
    tool_name: str | None = Field(None, description="Tool name")
    tool_call_id: str | None = Field(None, description="Tool call correlation ID")
    success: bool | None = Field(None, description="Whether tool execution succeeded")
    usage: dict[str, JsonValue] | None = Field(None, description="Accumulated model token usage")
