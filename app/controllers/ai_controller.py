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


# ==================== 健康检查 ====================


@router.get("/health", summary="健康检查")
async def health_check():
    """
    服务健康检查接口（无鉴权，白名单）

    返回服务运行状态，用于监控和负载均衡健康探测。
    """
    return Response.success(
        data={
            "status": "running",
            "version": "1.0.0",
            "service": "FastAPI AI Service",
        },
        msg="服务运行正常",
    )


# ==================== 预留 AI 接口 ====================


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
    """获取当前登录用户的 AI 对话列表"""
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
    """获取当前登录用户的 AI 对话详情"""
    data = await AIService.get_chat_log_detail(db, chat_id, current_user.get("user_id") or 0)
    return Response.success(data=data)


@router.delete("/ai/chats/{chat_id}", summary="删除 AI 对话")
async def delete_chat(
    chat_id: int,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """删除当前登录用户的指定 AI 对话"""
    data = await AIService.delete_chat_log(db, chat_id, current_user.get("user_id") or 0)
    return Response.success(data=data, msg="删除成功")

