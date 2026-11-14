"""
============================================
websocket主控制器
============================================
职责：只负责路由定义、接收请求、参数校验、返回响应。
主要用于websocket的消息接收和发送接收监听信息
"""
from fastapi import Depends, HTTPException,APIRouter,WebSocket,WebSocketDisconnect

from app.services.websocket.manager import  manager

# ==================== 路由定义 ====================
router = APIRouter(prefix = "/common/ws",tags="websocket链接")


@router.websocket("/chat")
async def websocket_endpoint(ws:WebSocket)->None:
    await manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            await manager.broadcast(f"{id(ws)}:{data}",exclude=ws)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)
        await manager.broadcast("a client left th chat")



