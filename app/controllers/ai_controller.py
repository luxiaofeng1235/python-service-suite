"""
============================================
AI 接口控制器层
============================================
负责 AI 对话、流式输出等接口定义。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PageParams
from app.common.response import Response
from app.core.dependency import get_current_user
from app.database import get_session
from app.schemas.ai import ChatRequest
from app.services.ai_service import AIService
from app.utils.sse import SSEUtil

# ==================== 路由定义 ====================
router = APIRouter(prefix="/api", tags=["AI 服务"])


@router.post("/ai/chat", summary="AI 对话")
async def chat(
    req: ChatRequest,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """
    AI 对话接口

    - 接收用户消息
    - 返回完整回复
    """
    data = await AIService.chat(db, req, user_id=current_user.get("user_id") or 0)
    return Response.success(data=data, msg="调用成功")


@router.post("/ai/chat/send_stream_sse", summary="AI 流式对话(SSE)")
async def chat_stream(
    req: ChatRequest,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """
    AI 流式对话接口

    - 接收用户消息
    - SSE 推送分片响应
    """
    return SSEUtil.stream_response(
        AIService.stream_chat(db, req, user_id=current_user.get("user_id") or 0),
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
        page_params: 分页参数（page, page_size）
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
    data = await AIService.delete_chat_log(db, chat_id, current_user.get("user_id") or 0)
    return Response.success(data=data, msg="删除成功")
