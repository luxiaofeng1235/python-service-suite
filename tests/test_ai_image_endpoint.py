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
    return {"model": 1, "prompt": "一只小猫", "size": "1024~1024",
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
    query = {"task_id": "image-task-1"}
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


async def test_four_images_are_saved_and_returned_as_a_url_array(image_api, monkeypatch):
    _, client, requests, responses, sessions = image_api
    task_id = "72ddf3a4-0aa9-4e8e-bee3-12ccf10d487d"
    prefix = "https://static.jsss999.com"
    monkeypatch.setattr(settings, "FILE_BASE_URL", prefix)
    upstream_urls = [f"https://images.test/{index}.png" for index in range(1, 5)]
    responses.extend([
        httpx.Response(200, json={"output": {"task_id": task_id}}),
        httpx.Response(200, json={"output": {
            "task_status": "SUCCEEDED", "results": [{"url": url} for url in upstream_urls],
        }}),
    ])
    downloads = []

    async def save_image(url, image_task_id, index, *, watermark=False):
        downloads.append((url, image_task_id, index, watermark))
        return f"ai_images/{image_task_id}_{index}.png"

    monkeypatch.setattr("app.services.ai_image_service.save_generated_image", save_image)
    submitted = await client.post("/api/ai/to_image", json=payload(n=4, watermark=1))
    assert submitted.json() == {"code": 1, "msg": "图片生成中", "data": task_id}
    assert json.loads(requests[0].content)["parameters"]["n"] == 4

    finished = await client.get("/api/ai/get_image", params={"task_id": task_id})
    urls = [f"{prefix}/uploads/ai_images/{task_id}_{index}.png" for index in range(1, 5)]
    assert finished.json() == {
        "code": 1, "msg": "图片生成成功", "data": {"image": urls, "iamge": urls},
    }
    assert downloads == [(url, task_id, index, True) for index, url in enumerate(upstream_urls, 1)]
    async with sessions() as db:
        task = (await db.execute(select(AiToWork))).scalar_one()
        assert task.status == 1
        assert task.params["n"] == 4
        assert task.work == urls

    cached = await client.get("/api/ai/get_image", params={"task_id": task_id})
    assert cached.json() == finished.json()
    assert len(requests) == 2
    assert len(downloads) == 4


@pytest.mark.parametrize("legacy_json", [False, True])
async def test_php_four_image_array_is_compatible_with_cached_queries(image_api, legacy_json):
    _, client, requests, _, sessions = image_api
    task_id = "72ddf3a4-0aa9-4e8e-bee3-12ccf10d487d"
    urls = [f"https://static.jsss999.com/uploads/ai_images/{task_id}_{index}.png" for index in range(1, 5)]
    async with sessions() as db:
        db.add(AiToWork(
            user_id=7, task_id=task_id, params={"n": 4}, type=1, status=1,
            work=json.dumps(urls) if legacy_json else urls,
        ))
        await db.commit()

    response = await client.get("/api/ai/get_image", params={"task_id": task_id})
    assert response.json() == {
        "code": 1, "msg": "图片生成成功", "data": {"image": urls, "iamge": urls},
    }
    assert requests == []


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
    {"n": 0}, {"n": 5}, {"watermark": 0}, {"watermark": 3},
])
async def test_invalid_php_parameters_return_unified_validation_errors(image_api, change):
    _, client, requests, _, _ = image_api
    response = await client.post("/api/ai/to_image", json=payload(**change))
    assert response.status_code == 422
    assert response.json()["code"] == 422
    assert response.json()["msg"].startswith("参数校验失败")
    assert requests == []


@pytest.mark.parametrize("missing", ["model", "prompt", "size", "n", "watermark"])
async def test_submission_requires_all_php_fields(image_api, missing):
    _, client, requests, _, _ = image_api
    body = payload()
    del body[missing]
    response = await client.post("/api/ai/to_image", json=body)
    assert response.status_code == 422
    assert requests == []


@pytest.mark.parametrize("query", [{}, {"task_id": ""}, {"task_id": "t" * 256}])
async def test_progress_requires_valid_task_id(image_api, query):
    _, client, requests, _, _ = image_api
    response = await client.get("/api/ai/get_image", params=query)
    assert response.status_code == 422
    assert response.json()["code"] == 422
    assert requests == []


async def test_submission_uses_token_user_even_with_extra_user_id(image_api):
    _, client, requests, responses, sessions = image_api
    responses.append(httpx.Response(200, json={"output": {"task_id": "image-task-1"}}))
    submitted = await client.post("/api/ai/to_image", json=payload(user_id=99))
    assert submitted.json()["code"] == 1
    async with sessions() as db:
        task = (await db.execute(select(AiToWork))).scalar_one()
        assert task.user_id == 7
        assert "user_id" not in task.params
    assert len(requests) == 1


async def test_progress_is_scoped_to_token_user_even_with_extra_user_id(image_api):
    _, client, requests, _, sessions = image_api
    async with sessions() as db:
        db.add_all([
            AiToWork(user_id=7, task_id="own-task", params={}, type=1, status=1,
                     work=["/uploads/own.png"]),
            AiToWork(user_id=99, task_id="other-task", params={}, type=1, status=1,
                     work=["/uploads/other.png"]),
        ])
        await db.commit()
    own = await client.get("/api/ai/get_image", params={"user_id": 99, "task_id": "own-task"})
    assert own.json()["data"]["image"] == ["/uploads/own.png"]
    other = await client.get("/api/ai/get_image", params={"user_id": 99, "task_id": "other-task"})
    assert other.json() == {"code": 0, "msg": "任务不存在", "data": None}
    assert requests == []


async def test_routes_require_login(image_api):
    app, client, requests, _, _ = image_api
    del app.dependency_overrides[get_current_user]
    submitted = await client.post("/api/ai/to_image", json=payload())
    progress = await client.get("/api/ai/get_image", params={"task_id": "task"})
    assert submitted.status_code == progress.status_code == 401
    assert requests == []


async def test_generation_failure_uses_unified_business_response(image_api):
    _, client, _, responses, _ = image_api
    responses.extend([
        httpx.Response(200, json={"output": {"task_id": "image-task-1"}}),
        httpx.Response(200, json={"output": {"task_status": "FAILED", "code": "DataInspectionFailed"}}),
    ])
    await client.post("/api/ai/to_image", json=payload())
    query = {"task_id": "image-task-1"}
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
    paths = app.openapi()["paths"]
    body = paths["/api/ai/to_image"]["post"]["requestBody"]
    for media_type in ("application/json", "application/x-www-form-urlencoded", "multipart/form-data"):
        schema = body["content"][media_type]["schema"]
        assert schema["properties"]["size"]["type"] == "string"
        assert "user_id" not in schema["properties"]
        assert "user_id" not in schema["required"]
    parameters = paths["/api/ai/get_image"]["get"]["parameters"]
    assert [parameter["name"] for parameter in parameters] == ["task_id"]
