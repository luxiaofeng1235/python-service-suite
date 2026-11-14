"""
============================================
WebSocket 连接管理服务 - 单播与广播
============================================
按设备标识管理当前进程内的连接，提供文本发送、超时控制和断线清理。
不绑定鉴权或具体业务，同一设备标识重新连接时替换旧连接。
"""

import asyncio
import json

from fastapi import WebSocket

from app.core.config import settings
from app.pkg.logging import ws_logger


class ConnectionManager:
    """管理当前进程的 WebSocket 连接及消息发送。"""

    def __init__(self, *, send_timeout: float | None = None) -> None:
        """初始化连接记录和每条连接的发送锁。"""
        self.active_connections: dict[str, WebSocket] = {}
        self._send_locks: dict[WebSocket, asyncio.Lock] = {}
        self.send_timeout = (
            settings.WEBSOCKET_SEND_TIMEOUT if send_timeout is None else send_timeout
        )
        if self.send_timeout <= 0:
            raise ValueError("WebSocket 发送超时必须大于 0 秒")

    async def connect(self, ws: WebSocket, client_id: str | None = None) -> str:
        """接受并登记连接；未提供设备标识时，使用连接对象 ID 并返回标识。"""
        connection_id = str(id(ws)) if client_id is None else client_id
        if not connection_id.strip():
            raise ValueError("设备标识不能为空")

        await ws.accept()
        previous = self.active_connections.get(connection_id)
        self.active_connections[connection_id] = ws
        self._send_locks[ws] = asyncio.Lock()

        if previous is not None and previous is not ws:
            await self.disconnect(previous)
            try:
                await self._close_connection(previous)
            except asyncio.CancelledError:
                # 控制器尚未进入收发循环，此时取消需要由连接方法清理登记。
                await self.disconnect(ws)
                raise
        return connection_id

    async def disconnect(self, ws: WebSocket) -> None:
        """移除指定连接，可重复调用；旧连接退出时保留同设备的新连接。"""
        for client_id, connection in list(self.active_connections.items()):
            if connection is ws:
                self.active_connections.pop(client_id, None)
        self._send_locks.pop(ws, None)

    async def send_personal_message(self, client_id: str, message: str) -> bool:
        """向指定设备发送文本；连接不存在或发送失败时返回 False。"""
        ws = self.active_connections.get(client_id)
        if ws is None:
            return False
        return await self._send_message(client_id, ws, message)

    async def broadcast(self, message: str, *, exclude: WebSocket | None = None) -> None:
        """并发广播文本，可排除发送者；慢连接不阻塞其他连接接收。"""
        # 使用快照，避免发送期间的连接增减影响本轮广播。
        await asyncio.gather(
            *(
                self._send_message(client_id, ws, message)
                for client_id, ws in list(self.active_connections.items())
                if ws is not exclude
            )
        )

    async def dispatch_message(self, ws: WebSocket, client_id: str, message: str) -> bool:
        """普通文本广播；JSON 按 type 分发，单播通过 to 指定接收方。"""
        if self.active_connections.get(client_id) is not ws:
            return False
        if not message.lstrip().startswith("{"):
            await self.broadcast(f"{client_id}:{message}", exclude=ws)
            return True

        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return await self._send_message(client_id, ws, "消息格式错误，请发送有效的 JSON")

        message_type = payload.get("type")
        content = payload.get("message")
        if message_type not in ("personal", "broadcast") or not isinstance(content, str):
            return await self._send_message(client_id, ws, "消息需包含有效的 type 和文本 message")

        if message_type == "personal":
            target = payload.get("to")
            if not isinstance(target, str) or not target.strip():
                return await self._send_message(client_id, ws, "单播消息必须提供接收方 to")
            if not await self.send_personal_message(target, f"{client_id}:{content}"):
                return await self._send_message(client_id, ws, "接收方不在线或消息发送失败")
            return True

        if payload.get("to") is not None:
            return await self._send_message(client_id, ws, "广播消息不应提供接收方 to")
        await self.broadcast(f"{client_id}:{content}", exclude=ws)
        return True

    async def _send_message(self, client_id: str, ws: WebSocket, message: str) -> bool:
        """同一连接串行发送，发送超时或异常时清理并尝试关闭连接。"""
        lock = self._send_locks.get(ws)
        if lock is None:
            return False

        try:
            # 超时包含等待发送锁的时间，避免消息在慢连接上无限堆积。
            async with asyncio.timeout(self.send_timeout):
                async with lock:
                    if self.active_connections.get(client_id) is not ws:
                        return False
                    await ws.send_text(message)
            return True
        except Exception as exc:
            # 不捕获 CancelledError，让调用方能正常取消任务。
            ws_logger.warning("WebSocket 发送失败，异常类型={}", type(exc).__name__)
            await self.disconnect(ws)
            await self._close_connection(ws)
            return False

    async def _close_connection(self, ws: WebSocket) -> None:
        """尝试关闭已失效或被替换的连接，关闭过程也受超时限制。"""
        try:
            async with asyncio.timeout(self.send_timeout):
                await ws.close(code=1001, reason="连接已失效或已被替换")
        except Exception as exc:
            ws_logger.debug("WebSocket 连接关闭失败，异常类型={}", type(exc).__name__)


# 当前进程共用的连接管理实例。
manager = ConnectionManager()

