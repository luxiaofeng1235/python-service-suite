"""
============================================
Agent 对话模型 - 请求参数与流式事件
============================================
定义与模型厂商及 Agent 框架无关的请求、文字分片和结构化业务数据协议。
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class AgentChatRequest(BaseModel):
    """接收一条用户消息，可指定已有会话。"""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=4000, description="用户消息")
    session_id: UUID | None = Field(None, description="已有会话 UUID，未传时创建新会话")

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        """拒绝纯空白消息，保留用户原始文本。"""
        if not value.strip():
            raise ValueError("消息内容不能为空")
        return value


class AgentStreamEvent(BaseModel):
    """统一输出文字、工具状态和结构化业务数据事件。"""

    type: Literal[
        "session", "delta", "reasoning", "tool_start", "tool_end", "data", "done", "error"
    ] = Field(..., description="流式事件类型")
    session_id: str = Field(..., description="会话 UUID")
    agent: str = Field(..., description="Agent 标识")
    message_id: int | None = Field(None, description="已保存的消息 ID")
    content: str | None = Field(None, description="文字分片或面向用户的状态说明")
    tool_name: str | None = Field(None, description="工具名称")
    tool_call_id: str | None = Field(None, description="工具调用关联 ID")
    success: bool | None = Field(None, description="工具是否执行成功")
    usage: dict[str, JsonValue] | None = Field(None, description="累计模型 Token 用量")
    data: dict[str, JsonValue] | None = Field(
        None, description="后端结构化业务数据，kind 标记数据类型，例如 products 商品列表"
    )
