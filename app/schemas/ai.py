"""
============================================
AI 对话数据模型模块
============================================
定义 AI 对话相关的请求体、响应体。
"""

import json
from typing import Annotated, Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, WithJsonSchema, field_validator

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


class SendStreamRequest(ChatRequest):
    """Required parameters for the PHP-compatible streaming endpoint."""

    chat_id: int = Field(..., ge=0, description="Chat ID; use 0 for a new conversation")
    restart: int = Field(..., ge=0, le=1, description="Regenerate the reply: 0=no, 1=yes")


class ChatTTSRequest(BaseModel):
    """Text to synthesize using backend TTS settings."""

    text: str = Field(..., min_length=1, max_length=600, description="Text to synthesize")

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Reject whitespace-only input without altering the spoken text."""
        if not value.strip():
            raise ValueError("合成文本不能为空")
        return value


class OmniMessage(BaseModel):
    """Preserve text and structured multimodal message content."""

    role: str = Field(..., min_length=1, description="Message role")
    content: str | list[dict[str, Any]] = Field(
        ..., description="Text or structured image, audio and video content"
    )

    # 保留音频标识等消息附加字段，避免改写前端传入的多模态结构。
    model_config = ConfigDict(extra="allow")


class OmniStreamRequest(BaseModel):
    """Accept the PHP message field and its messages alias."""

    message: list[OmniMessage] = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("message", "messages"),
        description="Complete conversation messages for this request",
    )

    @field_validator("message", mode="before")
    @classmethod
    def parse_messages(cls, value: Any) -> Any:
        """Normalize PHP form values while preserving message arrays."""
        if not isinstance(value, str):
            return value
        try:
            decoded = json.loads(value)
        except ValueError:
            decoded = None
        if isinstance(decoded, list):
            return decoded
        # 与 PHP 一致：表单字段可传 JSON 数组字符串，也可传普通文本。
        text = value.strip()
        if not text:
            raise ValueError("消息内容不能为空")
        return [{"role": "user", "content": text}]


class ImageRequest(BaseModel):
    """Image parameters matching AiLogic.php toImage."""

    model: int = Field(..., ge=1, le=2, description="Image model: 1=turbo 2=plus")
    prompt: str = Field(..., min_length=1, max_length=500, description="Text-to-image prompt")
    size: tuple[int, int] = Field(..., description="Image size as [width, height]")
    n: int = Field(..., ge=1, le=4, description="Number of images")
    watermark: int = Field(..., ge=1, le=2, description="Watermark: 1=on 2=off")

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        """Reject empty prompts without changing user input."""
        if not value.strip():
            raise ValueError("提示词不能为空")
        return value

    @field_validator("size")
    @classmethod
    def validate_size(cls, value: tuple[int, int]) -> tuple[int, int]:
        """Validate the dimensions and pixel limit from the PHP controller."""
        if any(dimension < 720 or dimension > 1440 for dimension in value):
            raise ValueError("size格式错误，宽高必须在720到1440之间")
        if value[0] * value[1] > 2_000_000:
            raise ValueError("尺寸过大，像素不能超过200万")
        return value


class ToImageRequest(ImageRequest):
    """PHP-compatible image API parameters, normalized for the core service."""

    size: Annotated[
        tuple[int, int],
        WithJsonSchema({"type": "string", "examples": ["1024~1024"]}),
    ] = Field(..., description="Image size as width~height, e.g. 1024~1024")

    @field_validator("size", mode="before")
    @classmethod
    def parse_size(cls, value: Any) -> tuple[int, int]:
        """Convert the PHP size string into integer dimensions."""
        if not isinstance(value, str):
            raise ValueError("size格式错误，请使用宽~高，例如1024~1024")
        dimensions = value.split("~")
        if len(dimensions) != 2 or not all(part.isascii() and part.isdigit() for part in dimensions):
            raise ValueError("size格式错误，请使用宽~高，例如1024~1024")
        return int(dimensions[0]), int(dimensions[1])


class VideoRequest(BaseModel):
    """PHP-compatible text-to-video parameters for the to=2 workflow."""

    to: int = Field(2, ge=2, le=2, description="Generation type: 2=text-to-video")
    prompt: str = Field(..., min_length=1, max_length=500, description="Text-to-video prompt")

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        """Reject empty prompts without changing user input."""
        if not value.strip():
            raise ValueError("提示词不能为空")
        return value


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
