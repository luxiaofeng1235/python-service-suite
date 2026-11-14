"""
============================================
WebSocket 连接管理测试 - 收发与异常清理
============================================
验证单播、广播、重连和发送超时，不依赖数据库或外部网络。
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from app.api.controllers.ws_controller import router
from app.services.websocket.manager import ConnectionManager, manager


def _socket() -> MagicMock:
    """创建可以控制发送行为的连接替身。"""
    ws = MagicMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.mark.parametrize("client_id", [None, "device-1"])
async def test_connect_registers_personal_message_target(client_id: str | None) -> None:
    """默认连接方式和指定设备方式均可登记并用于单播。"""
    connections = ConnectionManager()
    ws = _socket()
    other = _socket()
    registered_id = await connections.connect(ws, client_id)
    await connections.connect(other, "other")

    assert registered_id == (str(id(ws)) if client_id is None else client_id)
    assert await connections.send_personal_message(registered_id, "你好") is True
    ws.accept.assert_awaited_once()
    ws.send_text.assert_awaited_once_with("你好")
    other.send_text.assert_not_awaited()


async def test_missing_device_returns_false() -> None:
    """目标设备不在线时，单播返回 False。"""
    assert await ConnectionManager().send_personal_message("missing", "你好") is False


async def test_disconnect_is_safe_after_send_failure() -> None:
    """发送失败已清理的连接可以再次断开，不产生 KeyError。"""
    connections = ConnectionManager()
    ws = _socket()
    ws.send_text.side_effect = OSError("连接已关闭")
    await connections.connect(ws, "device")

    assert await connections.send_personal_message("device", "你好") is False
    await connections.disconnect(ws)
    await connections.disconnect(ws)

    assert connections.active_connections == {}
    ws.close.assert_awaited_once()


async def test_reconnect_keeps_new_connection_after_old_disconnect() -> None:
    """同设备重连替换旧连接，旧控制器清理时不删除新连接。"""
    connections = ConnectionManager()
    old, new = _socket(), _socket()
    await connections.connect(old, "device")
    await connections.connect(new, "device")
    await connections.disconnect(old)

    old.close.assert_awaited_once()
    assert await connections.send_personal_message("device", "重连成功") is True
    new.send_text.assert_awaited_once_with("重连成功")


async def test_old_send_failure_does_not_remove_reconnected_device() -> None:
    """旧连接发送尚未结束时发生重连，迟到的失败不能删除新连接。"""
    connections = ConnectionManager()
    old, new = _socket(), _socket()
    started, release = asyncio.Event(), asyncio.Event()

    async def fail_later(message: str) -> None:
        """在测试触发重连后再模拟旧连接失败。"""
        started.set()
        await release.wait()
        raise OSError("旧连接已断开")

    old.send_text.side_effect = fail_later
    await connections.connect(old, "device")
    sending = asyncio.create_task(connections.send_personal_message("device", "旧消息"))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        await connections.connect(new, "device")
        release.set()
        assert await asyncio.wait_for(sending, timeout=1) is False
        assert connections.active_connections["device"] is new
        assert await connections.send_personal_message("device", "新消息") is True
    finally:
        sending.cancel()
        await asyncio.gather(sending, return_exceptions=True)


async def test_cancelled_reconnect_does_not_leave_registered_connection() -> None:
    """替换旧连接期间被取消时，清理尚未交给控制器的新连接记录。"""
    connections = ConnectionManager()
    old, new = _socket(), _socket()
    closing = asyncio.Event()

    async def block_close(*, code: int, reason: str) -> None:
        """在旧连接关闭期间保持等待。"""
        closing.set()
        await asyncio.Event().wait()

    old.close.side_effect = block_close
    await connections.connect(old, "device")
    reconnecting = asyncio.create_task(connections.connect(new, "device"))
    try:
        await asyncio.wait_for(closing.wait(), timeout=1)
    finally:
        reconnecting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await reconnecting
    assert connections.active_connections == {}


async def test_broadcast_delivers_to_healthy_peer_while_slow_peer_times_out() -> None:
    """慢连接等待发送时其他客户端仍能接收，超时后慢连接被清理。"""
    connections = ConnectionManager(send_timeout=0.1)
    slow, healthy, sender = _socket(), _socket(), _socket()
    healthy_received = asyncio.Event()

    async def block_send(message: str) -> None:
        """模拟一直无法完成发送的客户端。"""
        await asyncio.Event().wait()

    async def receive_message(message: str) -> None:
        """记录正常客户端已收到广播。"""
        healthy_received.set()

    slow.send_text.side_effect = block_send
    healthy.send_text.side_effect = receive_message
    await connections.connect(slow, "slow")
    await connections.connect(healthy, "healthy")
    await connections.connect(sender, "sender")

    sending = asyncio.create_task(connections.broadcast("广播", exclude=sender))
    try:
        await asyncio.wait_for(healthy_received.wait(), timeout=1)
        assert not sending.done()
        await asyncio.wait_for(sending, timeout=1)
    finally:
        sending.cancel()
        await asyncio.gather(sending, return_exceptions=True)

    assert "slow" not in connections.active_connections
    assert connections.active_connections["healthy"] is healthy
    slow.close.assert_awaited_once()
    sender.send_text.assert_not_awaited()


async def test_personal_and_broadcast_sends_are_serialized_per_connection() -> None:
    """同一连接上的单播和广播不能同时执行底层发送。"""
    connections = ConnectionManager()
    ws = _socket()
    started, release = asyncio.Event(), asyncio.Event()
    active_sends = 0
    peak_sends = 0

    async def record_send(message: str) -> None:
        """第一条消息等待释放，记录是否出现重叠发送。"""
        nonlocal active_sends, peak_sends
        active_sends += 1
        peak_sends = max(peak_sends, active_sends)
        started.set()
        try:
            await release.wait()
        finally:
            active_sends -= 1

    ws.send_text.side_effect = record_send
    await connections.connect(ws, "device")
    personal = asyncio.create_task(connections.send_personal_message("device", "单播"))
    broadcast = None
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        broadcast = asyncio.create_task(connections.broadcast("广播"))
        await asyncio.sleep(0)
        release.set()
        assert await asyncio.wait_for(personal, timeout=1) is True
        await asyncio.wait_for(broadcast, timeout=1)
    finally:
        tasks = [personal] if broadcast is None else [personal, broadcast]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    assert peak_sends == 1
    assert ws.send_text.await_count == 2


async def test_send_cancellation_propagates() -> None:
    """调用方取消发送时保留取消信号，不误报发送成功。"""
    connections = ConnectionManager()
    ws = _socket()
    started = asyncio.Event()

    async def block_send(message: str) -> None:
        """保持发送等待，供测试取消。"""
        started.set()
        await asyncio.Event().wait()

    ws.send_text.side_effect = block_send
    await connections.connect(ws, "device")
    sending = asyncio.create_task(connections.send_personal_message("device", "你好"))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
    finally:
        sending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await sending
    await connections.disconnect(ws)


def test_existing_controller_still_supports_text_round_trip() -> None:
    """验证现有控制器无需调整连接参数即可双向广播和正常退出。"""
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        with client.websocket_connect("/common/ws/chat") as first:
            with client.websocket_connect("/common/ws/chat") as second:
                first.send_text("你好")
                assert second.receive_text().endswith(":你好")
                second.send_text("收到")
                assert first.receive_text().endswith(":收到")
            assert first.receive_text() == "a client left th chat"
    assert manager.active_connections == {}
