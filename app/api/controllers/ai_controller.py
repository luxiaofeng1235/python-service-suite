"""
============================================
AI 接口控制器层
============================================
负责 AI 对话、流式输出等接口定义。
"""

import json
from typing import TypeVar

from fastapi import APIRouter, Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.services.ai_service import AIService
from app.common.pagination import PageParams
from app.common.response import Response
from app.core.dependency import get_current_user
from app.database import get_session
from app.schemas.ai import ChatRequest, SendStreamRequest, ToImageRequest, VideoRequest
from app.utils.sse import SSEUtil

# ==================== 路由定义 ====================
router = APIRouter(prefix="/api", tags=["AI 服务"])
AIRequest = TypeVar("AIRequest", bound=BaseModel)


async def _parse_ai_request(request: Request, schema: type[AIRequest]) -> AIRequest:
    """Read JSON or PHP-style form fields and validate a generation request."""
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    try:
        if content_type in {"application/x-www-form-urlencoded", "multipart/form-data"}:
            payload = dict(await request.form())
        else:
            payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RequestValidationError([
            {"type": "json_invalid", "loc": ("body",), "msg": "请求体不是有效JSON", "input": None}
        ]) from exc
    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        # 去掉异常对象上下文，交给项目统一校验响应处理器序列化。
        errors = [
            {**error, "loc": ("body", *error["loc"])}
            for error in exc.errors(include_context=False)
        ]
        raise RequestValidationError(errors, body=payload) from exc


async def _parse_to_image_request(request: Request) -> ToImageRequest:
    """Validate an image request using the shared body parser."""
    return await _parse_ai_request(request, ToImageRequest)


async def _parse_to_video_request(request: Request) -> VideoRequest:
    """Validate a text-to-video request using the shared body parser."""
    return await _parse_ai_request(request, VideoRequest)


@router.post(
    "/ai/to_video",
    summary="提交AI文生视频任务",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                media_type: {"schema": VideoRequest.model_json_schema()}
                for media_type in ("application/json", "application/x-www-form-urlencoded", "multipart/form-data")
            },
        },
    },
)
async def to_video(
    req: VideoRequest = Depends(_parse_to_video_request),
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Submit a text-to-video task for the authenticated user."""
    task_id = await AIService.to_video(db, req, user_id=current_user["user_id"])
    return Response.success(data=task_id, msg="视频生成中")


@router.get("/ai/get_video", summary="获取AI视频进度和带水印的结果")
async def get_video(
    task_id: str = Query(..., min_length=1, max_length=255, description="文生视频任务ID"),
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Return progress or the published watermarked video URLs."""
    result = await AIService.get_video(db, task_id, user_id=current_user["user_id"])
    return Response.success(
        data=result, msg="视频生成中" if isinstance(result, str) else "视频生成成功",
    )


@router.post(
    "/ai/to_image",
    summary="提交AI文生图任务",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                media_type: {"schema": ToImageRequest.model_json_schema()}
                for media_type in ("application/json", "application/x-www-form-urlencoded", "multipart/form-data")
            },
        },
    },
)
async def to_image(
    req: ToImageRequest = Depends(_parse_to_image_request),
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Submit a validated image task for the authenticated user."""
    task_id = await AIService.to_image(
        db,
        req,
        user_id=current_user["user_id"],
    )
    return Response.success(data=task_id, msg="图片生成中")


@router.get("/ai/get_image", summary="获取AI生图进度和结果")
async def get_image(
    task_id: str = Query(..., min_length=1, max_length=255, description="文生图任务ID"),
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Return image progress or the completed image URLs."""
    result = await AIService.get_image(
        db,
        task_id,
        user_id=current_user["user_id"],
    )
    return Response.success(
        data=result,
        msg="图片生成中" if isinstance(result, str) else "图片生成成功",
    )


@router.post(
    "/ai/chat/send_stream_sse",
    summary="AI 流式对话(SSE)",
    response_class=EventSourceResponse,
)
async def chat_stream(
    req: ChatRequest,
    current_user: dict = Depends(get_current_user),
) -> EventSourceResponse:
    """
    AI 流式对话接口

    - 接收用户消息
    - SSE 推送分片响应
    """
    return SSEUtil.stream_response(
        AIService.stream_chat(req, user_id=current_user.get("user_id") or 0),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/ai/chat/send_stream",
    summary="AI 流式对话",
    response_class=EventSourceResponse,
)
async def chat_stream_compatible(
    req: SendStreamRequest,
    current_user: dict = Depends(get_current_user),
) -> EventSourceResponse:
    """Stream a chat with required chat_id and restart fields."""
    return SSEUtil.stream_response(
        AIService.stream_chat(req, user_id=current_user.get("user_id") or 0),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/ai/chats", summary="AI 对话列表")
async def list_chats(
    page_params: PageParams = Depends(),
    model_id: int | None = Query(None, ge=1, le=1, description="模型类型：1 千问"),
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """
    获取当前登录用户的 AI 对话列表

    Args:
        page_params: 分页参数（page + page_size/size）
        model_id: 模型类型过滤（1=千问）

    Returns:
        分页后的对话列表
    """
    data = await AIService.list_chat_logs(
        db,
        user_id=current_user.get("user_id") or 0,
        page_params=page_params,
        model_id=model_id,
    )
    return Response.success(data=data)


@router.get("/ai/chats/{chat_id}", summary="AI 对话详情")
async def chat_detail(
    chat_id: int,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """
    获取当前登录用户的指定对话详情

    包含该对话下的所有消息记录，按创建时间升序排列。

    Args:
        chat_id: 对话 ID

    Returns:
        对话详情（含消息列表）
    """
    data = await AIService.get_chat_log_detail(db, chat_id, current_user.get("user_id") or 0)
    return Response.success(data=data)


@router.delete("/ai/chats/{chat_id}", summary="删除 AI 对话")
async def delete_chat(
    chat_id: int,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """
    删除当前登录用户的指定 AI 对话

    同时会删除该对话下的所有消息记录。只能删除自己的对话，越权访问会抛异常。

    Args:
        chat_id: 要删除的对话 ID

    Returns:
        被删除的对话记录
    """
    #获取当前的用户ID
    user_id = current_user.get("user_id") or 0
    data = await AIService.delete_chat_log(db, chat_id, user_id)
    return Response.success(data=data, msg="删除成功")
