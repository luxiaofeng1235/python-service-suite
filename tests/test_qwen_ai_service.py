"""
============================================
Qwen AI Service Tests
============================================
Verify model selection and OpenAI-compatible streaming without external requests.
"""

import json

import httpx
import pytest

from app.common.exception import AppException
from app.core.config import settings
from app.services.ai_service import AIService
from app.services.qwen_ai_service import QwenAIService
from app.utils.sse import SSEUtil


def test_resolve_config_selects_fixed_models_from_deep_reflection(monkeypatch):
    monkeypatch.setattr(settings, "QWEN_MODEL", "qwen-test-model")

    normal = QwenAIService.resolve_config(model_id=1)
    deep = QwenAIService.resolve_config(model_id=1, is_deep_reflection=1)

    assert normal.model == "qwen-max"
    assert deep.model == "qwq-plus"
    assert normal.enable_search is True
    assert "九界" not in normal.system_prompt
    assert "苏州" not in normal.system_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("is_deep_reflection", "expected_model"),
    [(0, "qwen-max"), (1, "qwq-plus")],
)
async def test_stream_completion_sends_search_request_and_yields_deltas(
    monkeypatch, is_deep_reflection, expected_model,
):
    monkeypatch.setattr(settings, "QWEN_API_KEY", "test-api-key")
    monkeypatch.setattr(settings, "QWEN_CHAT_URL", "https://qwen.test/chat/completions")
    monkeypatch.setattr(settings, "QWEN_MODEL", "qwen-test-model")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = "\n\n".join(
            [
                "data: "
                + json.dumps(
                    {"choices": [{"delta": {"reasoning_content": "思考中"}}]},
                    ensure_ascii=False,
                ),
                "data: "
                + json.dumps(
                    {"choices": [{"delta": {"content": "答案"}}]},
                    ensure_ascii=False,
                ),
                "data: [DONE]",
            ]
        )
        return httpx.Response(200, text=body)

    monkeypatch.setattr(
        QwenAIService,
        "_create_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    config = QwenAIService.resolve_config(
        model_id=1, is_deep_reflection=is_deep_reflection,
    )
    messages = [{"role": "user", "content": "测试"}]

    events = [event async for event in QwenAIService.stream_completion(messages, config)]

    assert events == [("reasoning", "思考中"), ("delta", "答案")]
    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bearer test-api-key"
    payload = json.loads(requests[0].content)
    assert payload == {
        "model": expected_model,
        "messages": messages,
        "stream": True,
        "enable_search": True,
    }


@pytest.mark.asyncio
async def test_stream_completion_raises_on_upstream_sse_error(monkeypatch):
    monkeypatch.setattr(settings, "QWEN_API_KEY", "test-api-key")
    monkeypatch.setattr(settings, "QWEN_CHAT_URL", "https://qwen.test/chat/completions")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text='data: {"error":{"message":"上游拒绝请求"}}\n\n',
        )

    monkeypatch.setattr(
        QwenAIService,
        "_create_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    config = QwenAIService.resolve_config(model_id=1)

    with pytest.raises(AppException, match="上游拒绝请求"):
        async for _ in QwenAIService.stream_completion([], config):
            pass


def test_php_stream_format_is_applied_only_at_output():
    assert AIService._format_stream_content("第一 行\n第二 行") == (
        "第一&nbsp;行<br/>第二&nbsp;行"
    )


def test_sse_response_sets_php_compatible_headers():
    async def stream():
        yield "chunk"

    response = SSEUtil.stream_response(
        stream(),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
