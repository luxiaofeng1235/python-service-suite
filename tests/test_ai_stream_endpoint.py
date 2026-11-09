"""Verify chat streaming, request validation, and authenticated user forwarding."""

import asyncio

import httpx
import pytest
from fastapi import FastAPI

from app.api.controllers import ai_controller
from app.core.dependency import get_current_user


@pytest.fixture
def api_app():
    app = FastAPI()
    app.include_router(ai_controller.router)

    async def current_user():
        return {"user_id": 7}

    app.dependency_overrides[get_current_user] = current_user
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["send_stream", "send_stream_sse"])
async def test_chat_stream_delivers_chunks_before_generation_finishes(
    api_app, monkeypatch, path,
):
    first_chunk_sent = asyncio.Event()
    calls = []

    async def stream_chat(req, user_id):
        calls.append((req, user_id))
        yield "第一段"
        await asyncio.wait_for(first_chunk_sent.wait(), timeout=2)
        yield '{"type":"reasoning_content","data":"思考"}'
        yield "[LOG_ID]:42"
        yield "[DONE]"

    monkeypatch.setattr(ai_controller.AIService, "stream_chat", stream_chat)

    async def observed_app(scope, receive, send):
        async def observed_send(message):
            await send(message)
            if (
                message["type"] == "http.response.body"
                and "第一段".encode() in message.get("body", b"")
            ):
                first_chunk_sent.set()

        await api_app(scope, receive, observed_send)

    payload = {"model": 1, "chat_id": 0, "msg": "你好", "restart": 0}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=observed_app), base_url="http://test",
    ) as client:
        response = await client.post(f"/api/ai/chat/{path}", json=payload)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.text.splitlines() == [
        "data: 第一段", "",
        'data: {"type":"reasoning_content","data":"思考"}', "",
        "data: [LOG_ID]:42", "",
        "data: [DONE]", "",
    ]
    assert calls[0][0].model_dump() == {**payload, "is_deep_reflection": 0}
    assert calls[0][1] == 7


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"chat_id": None},
        {"restart": None},
        {"restart": 2},
        {"model": 2},
        {"msg": ""},
    ],
)
async def test_chat_stream_rejects_invalid_parameters(api_app, monkeypatch, change):
    def unexpected_stream(*args, **kwargs):
        pytest.fail("Invalid parameters must be rejected before streaming starts")

    monkeypatch.setattr(ai_controller.AIService, "stream_chat", unexpected_stream)
    payload = {"model": 1, "chat_id": 0, "msg": "你好", "restart": 0}
    payload.update(change)
    payload = {key: value for key, value in payload.items() if value is not None}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_app), base_url="http://test",
    ) as client:
        response = await client.post("/api/ai/chat/send_stream", json=payload)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
