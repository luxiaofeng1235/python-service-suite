"""
============================================
AI Image Endpoint Tests
============================================
Exercise PHP-compatible image input, authentication, progress, and persistence locally.
"""

import json

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.controllers import ai_controller
from app.core.config import settings
from app.core.dependency import get_current_user
from app.database import get_session
from app.models.ai_to_work import AiToWork
from app.services.ai_image_service import AIImageService
from app.setup.exception import register_exception_handlers


@pytest.fixture
async def image_api(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(AiToWork.__table__.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    app = FastAPI()
    app.include_router(ai_controller.router)
    register_exception_handlers(app)

    async def session():
        async with sessions() as db:
            yield db

    async def user():
        return {"user_id": 7}

    app.dependency_overrides[get_session] = session
    app.dependency_overrides[get_current_user] = user
    monkeypatch.setattr(settings, "QWEN_API_KEY", "test-image-key")
    monkeypatch.setattr(settings, "QWEN_IMAGE_URL", "https://qwen.test/images")
    monkeypatch.setattr(settings, "QWEN_TASK_URL", "https://qwen.test/tasks")
    monkeypatch.setattr(settings, "FILE_BASE_URL", "")
    requests = []
    responses = []

    def handler(request):
        requests.append(request)
        if not responses:
            pytest.fail("Unexpected upstream image request")
        return responses.pop(0)

    monkeypatch.setattr(AIImageService, "_create_client", staticmethod(
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    ))

    async def save_image(url, task_id, index, *, watermark=False):
        return f"ai_images/{task_id}_{index}.png"

    monkeypatch.setattr("app.services.ai_image_service.save_generated_image", save_image)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        yield app, client, requests, responses, sessions
    await engine.dispose()


def payload(**changes):
    return {"user_id": 7, "model": 1, "prompt": "一只小猫", "size": "1024~1024",
            "n": 1, "watermark": 2} | changes


@pytest.mark.parametrize("encoding", ["json", "form", "multipart"])
async def test_php_image_submission_progress_success_and_cache(image_api, encoding):
    _, client, requests, responses, sessions = image_api
    responses.extend([
        httpx.Response(200, json={"output": {"task_id": "image-task-1"}}),
        httpx.Response(200, json={"output": {"task_status": "RUNNING"}}),
        httpx.Response(200, json={"output": {
            "task_status": "SUCCEEDED", "results": [{"url": "https://images.test/1.png"}],
        }}),
    ])
    if encoding == "json":
        options = {"json": payload()}
    elif encoding == "form":
        options = {"data": payload()}
    else:
        options = {"files": {key: (None, str(value)) for key, value in payload().items()}}
    submitted = await client.post("/api/ai/to_image", **options)
    assert submitted.status_code == 200
    assert submitted.json() == {"code": 1, "msg": "图片生成中", "data": "image-task-1"}
    assert json.loads(requests[0].content) == {
        "model": "wanx2.1-t2i-turbo", "input": {"prompt": "一只小猫"},
        "parameters": {"size": "1024*1024", "n": 1, "watermark": False},
    }
    assert requests[0].headers["Authorization"] == "Bearer test-image-key"
    async with sessions() as db:
        task = (await db.execute(select(AiToWork))).scalar_one()
        assert (task.user_id, task.status, task.work) == (7, 0, None)
        assert task.params == payload(size=[1024, 1024])
    query = {"user_id": 7, "task_id": "image-task-1"}
    pending = await client.get("/api/ai/get_image", params=query)
    assert pending.json() == submitted.json()
    finished = await client.get("/api/ai/get_image", params=query)
    assert finished.json() == {
        "code": 1, "msg": "图片生成成功",
        "data": {"image": ["/uploads/ai_images/image-task-1_1.png"],
                 "iamge": ["/uploads/ai_images/image-task-1_1.png"]},
    }
    cached = await client.get("/api/ai/get_image", params=query)
    assert cached.json() == finished.json()
    assert len(requests) == 3


@pytest.mark.parametrize("size", ["720~1280", "1440~720"])
async def test_php_size_boundaries_and_watermark_enabled(image_api, size):
    _, client, requests, responses, _ = image_api
    responses.append(httpx.Response(200, json={"output": {"task_id": "image-task-1"}}))
    response = await client.post("/api/ai/to_image", json=payload(
        model=2, prompt="图" * 500, size=size, n=4, watermark=1,
    ))
    assert response.json()["code"] == 1
    body = json.loads(requests[0].content)
    assert body["model"] == "wanx2.1-t2i-plus"
    assert body["parameters"] == {"size": size.replace("~", "*"), "n": 4, "watermark": False}


@pytest.mark.parametrize("change", [
    {"model": 0}, {"model": 3}, {"prompt": ""}, {"prompt": " "}, {"prompt": "图" * 501},
    {"size": "1024"}, {"size": "1024~1024~1024"}, {"size": "a~1024"},
    {"size": "720.5~1024"}, {"size": "719~1024"}, {"size": "1024~1441"},
    {"size": "1440~1440"}, {"size": [1024, 1024]},
    {"n": 0}, {"n": 5}, {"watermark": 0}, {"watermark": 3}, {"user_id": 0},
])
async def test_invalid_php_parameters_return_unified_validation_errors(image_api, change):
    _, client, requests, _, _ = image_api
    response = await client.post("/api/ai/to_image", json=payload(**change))
    assert response.status_code == 422
    assert response.json()["code"] == 422
    assert response.json()["msg"].startswith("参数校验失败")
    assert requests == []


@pytest.mark.parametrize("missing", ["user_id", "model", "prompt", "size", "n", "watermark"])
async def test_submission_requires_all_php_fields(image_api, missing):
    _, client, requests, _, _ = image_api
    body = payload()
    del body[missing]
    response = await client.post("/api/ai/to_image", json=body)
    assert response.status_code == 422
    assert requests == []


@pytest.mark.parametrize("query", [{}, {"user_id": 7}, {"task_id": "task"},
                                  {"user_id": 7, "task_id": ""}])
async def test_progress_requires_user_id_and_task_id(image_api, query):
    _, client, requests, _, _ = image_api
    response = await client.get("/api/ai/get_image", params=query)
    assert response.status_code == 422
    assert response.json()["code"] == 422
    assert requests == []


async def test_rejects_mismatched_user_id_on_both_routes(image_api):
    _, client, requests, _, _ = image_api
    submitted = await client.post("/api/ai/to_image", json=payload(user_id=99))
    progress = await client.get("/api/ai/get_image", params={"user_id": 99, "task_id": "task"})
    for response in (submitted, progress):
        assert response.json()["code"] == 0
        assert "当前登录用户不一致" in response.json()["msg"]
    assert requests == []


async def test_routes_require_login(image_api):
    app, client, requests, _, _ = image_api
    del app.dependency_overrides[get_current_user]
    submitted = await client.post("/api/ai/to_image", json=payload())
    progress = await client.get("/api/ai/get_image", params={"user_id": 7, "task_id": "task"})
    assert submitted.status_code == progress.status_code == 401
    assert requests == []


async def test_generation_failure_uses_unified_business_response(image_api):
    _, client, _, responses, _ = image_api
    responses.extend([
        httpx.Response(200, json={"output": {"task_id": "image-task-1"}}),
        httpx.Response(200, json={"output": {"task_status": "FAILED", "code": "DataInspectionFailed"}}),
    ])
    await client.post("/api/ai/to_image", json=payload())
    query = {"user_id": 7, "task_id": "image-task-1"}
    failed = await client.get("/api/ai/get_image", params=query)
    assert failed.json() == {"code": 0, "msg": "图片生成失败，敏感内容，生成失败", "data": None}
    assert (await client.get("/api/ai/get_image", params=query)).json() == failed.json()


async def test_malformed_json_returns_validation_response(image_api):
    _, client, requests, _, _ = image_api
    response = await client.post("/api/ai/to_image", content="{", headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["code"] == 422
    assert requests == []


async def test_openapi_documents_php_size_and_both_submission_formats(image_api):
    app, _, _, _, _ = image_api
    body = app.openapi()["paths"]["/api/ai/to_image"]["post"]["requestBody"]
    for media_type in ("application/json", "application/x-www-form-urlencoded", "multipart/form-data"):
        assert body["content"][media_type]["schema"]["properties"]["size"]["type"] == "string"
