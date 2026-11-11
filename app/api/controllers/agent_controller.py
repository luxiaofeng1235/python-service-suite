"""
============================================
Agent API Controller - Business Agent streams
============================================
Authenticates requests and exposes Agent services through the shared SSE transport.
"""

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.core.dependency import get_current_user
from app.schemas.agent.chat import AgentChatRequest
from app.services.agent.astrology_service import AstrologyService
from app.utils.sse import SSEUtil

router = APIRouter(prefix="/api/agent", tags=["Agent 服务"])


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
    """Stream an owned astrology conversation, creating a session when omitted."""
    return await SSEUtil.prepare_stream_response(
        AstrologyService().stream_sse(req, user_id=current_user["user_id"]),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
