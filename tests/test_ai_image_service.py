"""
============================================
AI Image Workflow Tests
============================================
Verify the PHP-compatible image workflow using SQLite and mocked DashScope responses.
"""

import json

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.services.ai_service import AIService
from app.common.exception import AppException
from app.core.config import settings
from app.models.ai_to_work import AiToWork
from app.schemas.ai import ImageRequest
from app.services.ai_image_service import AIImageService
from app.storage import ai_image


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(AiToWork.__table__.create)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def upstream(monkeypatch):
    monkeypatch.setattr(settings, "QWEN_API_KEY", "test-image-key")
    monkeypatch.setattr(settings, "QWEN_IMAGE_URL", "https://qwen.test/images")
    monkeypatch.setattr(settings, "QWEN_TASK_URL", "https://qwen.test/tasks")
    calls = []
    responses = []

    def handler(request):
        calls.append(request)
        if not responses:
            pytest.fail("Unexpected upstream request")
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(
        AIImageService,
        "_create_client",
        staticmethod(lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))),
    )
    return calls, responses


def image_request(**overrides):
    values = {"model": 1, "prompt": "一只小猫", "size": [1024, 1024], "n": 1, "watermark": 2}
    return ImageRequest(**(values | overrides))


async def add_task(db, **overrides):
    task = AiToWork(
        **({"user_id": 7, "task_id": "image-task-1", "params": {}, "type": 1,
            "status": 0, "work": []} | overrides)
    )
    db.add(task)
    await db.commit()
    return task


@pytest.mark.parametrize("model,expected", [(1, "wanx2.1-t2i-turbo"), (2, "wanx2.1-t2i-plus")])
async def test_to_image_submits_php_payload_and_persists_task(db, upstream, model, expected):
    calls, responses = upstream
    responses.append(httpx.Response(200, json={"output": {"task_id": "image-task-1"}}))
    req = image_request(model=model, size=[1024, 768], n=2, watermark=1)

    task_id = await AIService.to_image(db, req, user_id=7)

    assert task_id == "image-task-1"
    assert calls[0].headers["Authorization"] == "Bearer test-image-key"
    assert calls[0].headers["X-DashScope-Async"] == "enable"
    assert str(calls[0].url) == "https://qwen.test/images"
    assert json.loads(calls[0].content) == {
        "model": expected, "input": {"prompt": "一只小猫"},
        "parameters": {"size": "1024*768", "n": 2, "watermark": False},
    }
    task = (await db.execute(select(AiToWork))).scalar_one()
    assert (task.user_id, task.type, task.status) == (7, 1, 0)
    assert task.params == req.model_dump(mode="json")
    assert task.work is None


@pytest.mark.parametrize("length", [129, 255])
async def test_to_image_accepts_existing_table_task_id_length(db, upstream, length):
    _, responses = upstream
    task_id = "t" * length
    responses.append(httpx.Response(200, json={"output": {"task_id": task_id}}))
    assert await AIService.to_image(db, image_request(), 7) == task_id
    task = (await db.execute(select(AiToWork))).scalar_one()
    assert task.task_id == task_id
    assert task.work is None


async def test_to_image_rejects_task_ids_exceeding_existing_column(db, upstream):
    _, responses = upstream
    responses.append(httpx.Response(200, json={"output": {"task_id": "t" * 256}}))
    with pytest.raises(AppException):
        await AIService.to_image(db, image_request(), 7)
    assert (await db.execute(select(AiToWork))).scalars().all() == []


async def test_nullable_fields_match_existing_table(db):
    task = AiToWork(user_id=7, task_id=None, params={}, work=None,
                    create_time=None, update_time=None)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    assert task.task_id is None
    assert task.work is None
    assert (task.type, task.status) == (1, 0)


@pytest.mark.parametrize("overrides", [{"status": 3}, {"type": 2}])
async def test_deleted_and_video_tasks_are_not_returned(db, upstream, overrides):
    calls, _ = upstream
    task = await add_task(db, **overrides)
    with pytest.raises(AppException, match="任务不存在"):
        await AIService.get_image(db, task.task_id, 7)
    await db.refresh(task)
    assert calls == []
    for key, value in overrides.items():
        assert getattr(task, key) == value


@pytest.mark.parametrize("status", ["PENDING", "RUNNING", "SUSPENDED"])
async def test_get_image_returns_task_id_while_generating(db, upstream, status):
    calls, responses = upstream
    task = await add_task(db)
    responses.append(httpx.Response(200, json={"output": {"task_status": status}}))

    assert await AIService.get_image(db, task.task_id, 7) == task.task_id
    assert task.status == 0
    assert str(calls[0].url) == "https://qwen.test/tasks/image-task-1"
    assert calls[0].headers["Authorization"] == "Bearer test-image-key"
    assert "X-DashScope-Async" not in calls[0].headers


async def test_success_downloads_and_caches_results(db, upstream, monkeypatch):
    calls, responses = upstream
    task = await add_task(db)
    responses.append(httpx.Response(200, json={"output": {
        "task_status": "SUCCEEDED", "results": [{"url": "https://image.test/1.png"}],
    }}))
    downloads = []

    async def download(url, task_id, index, *, watermark=False):
        downloads.append((url, task_id, index))
        return "ai_images/result.png"

    monkeypatch.setattr("app.services.ai_image_service.save_generated_image", download)
    monkeypatch.setattr(settings, "FILE_BASE_URL", "https://files.test/")
    result = await AIService.get_image(db, task.task_id, 7)
    await db.refresh(task)
    assert result == {"image": ["https://files.test/uploads/ai_images/result.png"],
                      "iamge": ["https://files.test/uploads/ai_images/result.png"]}
    assert (task.status, task.work) == (1, result["image"])
    assert await AIService.get_image(db, task.task_id, 7) == result
    assert len(downloads) == len(calls) == 1


@pytest.mark.parametrize("params,enabled", [
    ({"watermark": 1}, True), ({"watermark": 2}, False),
    ('{"watermark":"1"}', True), ('{"watermark":"2"}', False),
])
async def test_saved_watermark_choice_controls_local_processing(db, upstream, monkeypatch, params, enabled):
    _, responses = upstream
    task = await add_task(db, params=params)
    responses.append(httpx.Response(200, json={"output": {
        "task_status": "SUCCEEDED", "results": [{"url": "https://image.test/1.png"}],
    }}))
    choices = []

    async def download(url, task_id, index, *, watermark=False):
        choices.append(watermark)
        return "ai_images/result.png"

    monkeypatch.setattr("app.services.ai_image_service.save_generated_image", download)
    await AIService.get_image(db, task.task_id, 7)
    assert choices == [enabled]
    assert task.status == 1


async def test_watermark_processing_failure_keeps_task_retryable(db, upstream, monkeypatch):
    _, responses = upstream
    task = await add_task(db, params={"watermark": 1})
    responses.append(httpx.Response(200, json={"output": {
        "task_status": "SUCCEEDED", "results": [{"url": "https://image.test/1.png"}],
    }}))

    async def fail_download(url, task_id, index, *, watermark=False):
        raise AppException(msg="图片水印处理失败")

    monkeypatch.setattr("app.services.ai_image_service.save_generated_image", fail_download)
    with pytest.raises(AppException, match="水印处理失败"):
        await AIService.get_image(db, task.task_id, 7)
    await db.refresh(task)
    assert task.status == 0
    assert task.work == []


@pytest.mark.parametrize("status,code,message", [
    ("FAILED", "DataInspectionFailed", "敏感内容"),
    ("UNKNOWN", None, "任务不存在"),
    ("CANCELED", None, "任务已取消"),
])
async def test_terminal_failures_are_persisted_and_cached(db, upstream, status, code, message):
    calls, responses = upstream
    task = await add_task(db)
    responses.append(httpx.Response(200, json={"output": {"task_status": status, "code": code}}))
    with pytest.raises(AppException, match=message):
        await AIService.get_image(db, task.task_id, 7)
    await db.refresh(task)
    assert task.status == 2
    assert message in task.work["error"]
    with pytest.raises(AppException, match=message):
        await AIService.get_image(db, task.task_id, 7)
    assert len(calls) == 1


async def test_other_users_cannot_query_or_modify_tasks(db, upstream):
    calls, _ = upstream
    task = await add_task(db)
    with pytest.raises(AppException, match="任务不存在"):
        await AIService.get_image(db, task.task_id, 99)
    assert calls == []
    assert task.status == 0


async def test_query_network_failure_is_retryable(db, upstream):
    _, responses = upstream
    task = await add_task(db)
    responses.append(httpx.ConnectError("network unavailable"))
    with pytest.raises(AppException, match="网络出错"):
        await AIService.get_image(db, task.task_id, 7)
    assert task.status == 0
    responses.append(httpx.Response(200, json={"output": {"task_status": "RUNNING"}}))
    assert await AIService.get_image(db, task.task_id, 7) == task.task_id


async def test_rejected_submission_creates_no_task(db, upstream):
    _, responses = upstream
    responses.append(httpx.Response(400, json={"code": "DataInspectionFailed"}))
    with pytest.raises(AppException, match="敏感内容"):
        await AIService.to_image(db, image_request(), 7)
    assert (await db.execute(select(AiToWork))).scalars().all() == []


@pytest.mark.parametrize("change", [
    {"model": 0}, {"model": 3}, {"size": [0, 1024]}, {"size": [1024]},
    {"prompt": "  "}, {"n": 0}, {"n": 5}, {"watermark": 0},
])
def test_invalid_image_parameters_are_rejected(change):
    with pytest.raises(ValidationError):
        image_request(**change)


async def test_download_writes_local_image_without_upstream_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    calls = []
    original_client = httpx.AsyncClient

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=b"generated-image", headers={"Content-Type": "image/png"})

    monkeypatch.setattr(ai_image.httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    path = await ai_image.save_generated_image("https://images.test/1.png", "../task", 1)
    assert (tmp_path / path).read_bytes() == b"generated-image"
    assert path.startswith("ai_images/")
    assert ".." not in path
    assert "Authorization" not in calls[0].headers
    assert list(tmp_path.rglob("*.tmp")) == []


async def test_oversized_download_cleans_temporary_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "FILE_IMAGE_MAX_SIZE", 3)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(ai_image.httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"too-large")),
        **kwargs,
    ))
    with pytest.raises(AppException, match="大小超过"):
        await ai_image.save_generated_image("https://images.test/1.png", "task", 1)
    assert list(tmp_path.rglob("*.png")) == []
    assert list(tmp_path.rglob("*.tmp")) == []
