"""
============================================
websocket链接服务，提供一套底座的通用服务能力
============================================
主要用于websocket的广播和单播消息通知推送，目前只做单独的发送消息不做任何业务绑定
"""

from typing import Set

import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

class ConnectionManager:
    def __init__(self) -> None:
        self.conns: Set[WebSocket] = set()

    def __init__(self)->None:
        #Set 比 list更加适合增删，+广播，且remote不受影响
        self.conns  = Set[WebSocket]()

    async  def connect(self, ws: WebSocket)->None:
        await ws.accept()
        self.conns.add(ws)

    async def disconnect(self, ws: WebSocket)->None:
        self.conns.remove(ws)

    async def broadcast(self, message: str, *, exclude: WebSocket | None = None) -> None:
        # 先取快照再发，避免迭代中被并发修改
        for ws in list(self.conns):
            if ws is exclude:
                continue
            try:
                await ws.send_text(message)
            except Exception:
                # 发送失败 = 这条连接已经死了，就地清理
                self.conns.discard(ws)

# 全局唯一单例
manager = ConnectionManager()

