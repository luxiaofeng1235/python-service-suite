"""
============================================
Agent 接口控制器 - 星座档案与业务对话
============================================
接收当前用户的星座档案查询、保存及流式对话请求，业务处理统一交给 Service。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse
from starlette.responses import JSONResponse

from app.common.response import Response
from app.core.dependency import get_current_user
from app.database import get_session
from app.schemas.agent.astrology import AstrologyProfileUpdateRequest
from app.schemas.agent.chat import AgentChatRequest
from app.services.agent.astrology_service import AstrologyService
from app.utils.sse import SSEUtil

router = APIRouter(prefix="/api/agent", tags=["Agent 服务"])


@router.get("/astrology/profile", summary="查询当前用户的星座档案")
async def get_astrology_profile(
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """读取当前登录用户的星座档案，未设置时返回 found=false。"""
    data = await AstrologyService.get_profile(db, current_user["user_id"])
    return Response.success(data, msg="星座档案查询成功")


@router.post("/astrology/profile", summary="保存当前用户的星座档案")
async def save_astrology_profile(
    req: AstrologyProfileUpdateRequest,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """首次保存创建档案，后续只更新本次明确提交的字段。"""
    data = await AstrologyService.update_profile(db, current_user["user_id"], req)
    return Response.success(data, msg="星座档案保存成功")


@router.post(
    "/astrology/stream",
    summary="星座 Agent 流式对话",
    response_class=EventSourceResponse,
    responses={
        200: {
            "description": "SSE 数据包含 session、delta、tool_start、tool_end、done 或 error 事件。",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
    },
)
async def astrology_stream(
    req: AgentChatRequest,
    current_user: dict = Depends(get_current_user),
) -> EventSourceResponse:
    """执行当前用户的星座流式对话，未传会话 ID 时创建新会话。"""
    return await SSEUtil.prepare_stream_response(
        AstrologyService().stream_sse(req, user_id=current_user["user_id"]),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
