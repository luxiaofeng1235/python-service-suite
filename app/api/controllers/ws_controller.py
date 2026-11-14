"""
============================================
WebSocket 控制器 - 连接与消息收发
============================================
接收可选的设备标识，将单播和广播的分发交给连接管理器。
"""

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.services.websocket.manager import manager

router = APIRouter(prefix="/common/ws", tags=["WebSocket 连接"])


@router.websocket("/chat")
async def websocket_endpoint(
    ws: WebSocket,
    client_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"\S",
        description="设备标识，省略时由后端分配",
    ),
) -> None:
    """建立支持单播和广播的 WebSocket 连接。"""
    connection_id = await manager.connect(ws, client_id=client_id)
    try:
        while True:
            message = await ws.receive_text()
            if not await manager.dispatch_message(ws, connection_id, message):
                break
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)
        await manager.broadcast("客户端已离线")
