"""
============================================
AI 对话数据模型模块
============================================
定义 AI 对话相关的请求体、响应体。
"""

from typing import Any

from pydantic import BaseModel, Field

# ==================== 请求体 ====================


class ChatRequest(BaseModel):
    """兼容旧链路的对话请求体"""

    model: int = Field(..., ge=1, le=1, description="模型类型：1 千问")
    chat_id: int = Field(0, ge=0, description="对话ID，0 表示新建对话")
    msg: str = Field(..., min_length=1, description="用户消息")
    restart: int = Field(0, ge=0, le=1, description="是否重生成：0否 1是")
    is_deep_reflection: int = Field(0, ge=0, le=1, description="是否深度思考")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "model": 1,
                    "chat_id": 0,
                    "msg": "你好，介绍一下这个服务",
                    "restart": 0,
                    "is_deep_reflection": 0,
                }
            ]
        }
    }


class ChatResponse(BaseModel):
    """对话响应体"""

    reply: str = Field(..., description="AI 回复内容")
    chat_id: int = Field(..., description="对话ID")
    usage: dict | None = Field(None, description="Token 使用统计")
    reasoning_content: str = Field("", description="深度思考内容")


class ChatLogResponse(BaseModel):
    """AI 对话记录响应体"""

    id: int = Field(..., description="对话ID")
    user_id: int = Field(..., description="用户ID")
    model_id: int = Field(..., description="模型类型")
    chat: list[dict[str, Any]] = Field(default_factory=list, description="聊天上下文")
    create_time: str | None = Field(None, description="创建时间")
    update_time: str | None = Field(None, description="更新时间")


class ChatLogListResponse(BaseModel):
    """AI 对话列表响应体"""

    items: list[ChatLogResponse] = Field(..., description="对话列表")
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    size: int = Field(..., description="每页条数")


class StreamChunk(BaseModel):
    """SSE 流式分片数据"""

    type: str = Field(..., description="分片类型：start/delta/reasoning/end/error")
    chat_id: int = Field(..., description="对话ID")
    content: str = Field("", description="当前分片内容")
    usage: dict | None = Field(None, description="结束时附带的统计信息")
    meta: dict[str, Any] | None = Field(None, description="附加元数据")
