"""
============================================
OSS Storage Tests - uploads and configuration
============================================
Exercise shared file, byte, URL, failure, and cached-image synchronization paths locally.
"""

from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.common.exception import AppException
from app.core.config import settings
from app.storage.ai_image import sync_generated_images
from app.storage.oss import OSSStorage


@pytest.fixture
def oss(monkeypatch):
    for key, value in {
        "OSS_ENABLED": True, "OSS_ACCESS_KEY_ID": "test-key", "OSS_ACCESS_KEY_SECRET": "test-secret",
        "OSS_ENDPOINT": "oss-cn-shanghai.aliyuncs.com", "OSS_REGION": "cn-shanghai",
        "OSS_BUCKET": "test-bucket", "OSS_VIEW_DOMAIN": "https://static.test/",
    }.items():
        monkeypatch.setattr(settings, key, value)

    class Bucket:
        def __init__(self):
            self.uploads = []
            self.existing = set()
            self.queries = []

        def put_object_from_file(self, key, filename, headers):
            self.uploads.append((key, Path(filename).read_bytes(), headers))
            self.existing.add(key)
            return SimpleNamespace(status=200)

        def put_object(self, key, content, headers):
            self.uploads.append((key, content, headers))
            self.existing.add(key)
            return SimpleNamespace(status=200)

        def object_exists(self, key):
            self.queries.append(key)
            return key in self.existing

    bucket = Bucket()
    monkeypatch.setattr(OSSStorage, "_create_bucket", staticmethod(lambda: bucket))
    return bucket


async def test_file_upload_uses_exact_object_key_and_content_type(oss, tmp_path):
    path = tmp_path / "image.png"
    path.write_bytes(b"image-content")
    url = await OSSStorage.upload_file(path, "uploads/ai_images/test_1.png")
    assert url == "https://static.test/uploads/ai_images/test_1.png"
    assert oss.uploads == [("uploads/ai_images/test_1.png", b"image-content", {"Content-Type": "image/png"})]


async def test_bytes_upload_encodes_public_url_without_changing_object_key(oss):
    key = "uploads/文件 name.txt"
    url = await OSSStorage.upload_bytes(b"hello", key, content_type="text/plain")
    assert url == "https://static.test/uploads/%E6%96%87%E4%BB%B6%20name.txt"
    assert oss.uploads == [(key, b"hello", {"Content-Type": "text/plain"})]


async def test_remote_upload_downloads_without_backend_credentials(oss, monkeypatch):
    calls = []
    original_client = httpx.AsyncClient

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=b"remote", headers={"Content-Type": "image/png"})

    monkeypatch.setattr("app.storage.oss.httpx.AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    url = await OSSStorage.upload_url("https://image.test/a.png", "uploads/images/a.png")
    assert url == "https://static.test/uploads/images/a.png"
    assert oss.uploads == [("uploads/images/a.png", b"remote", {"Content-Type": "image/png"})]
    assert "Authorization" not in calls[0].headers


async def test_remote_size_limit_prevents_upload(oss, monkeypatch):
    original_client = httpx.AsyncClient
    monkeypatch.setattr("app.storage.oss.httpx.AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"oversized")), **kwargs,
    ))
    with pytest.raises(AppException, match="大小超过"):
        await OSSStorage.upload_url("https://image.test/a.png", "uploads/a.png", max_size=2)
    assert oss.uploads == []


async def test_missing_config_prevents_upload(oss, monkeypatch):
    monkeypatch.setattr(settings, "OSS_ACCESS_KEY_SECRET", "")
    with pytest.raises(AppException, match="OSS_ACCESS_KEY_SECRET"):
        await OSSStorage.upload_bytes(b"image", "uploads/a.png")
    assert oss.uploads == []


@pytest.mark.parametrize("key", ["", "../secret", "uploads/../../secret", "uploads\\secret", "uploads/\x00"])
async def test_invalid_object_keys_are_rejected(oss, key):
    with pytest.raises(AppException, match="路径格式错误"):
        await OSSStorage.upload_bytes(b"image", key)
    assert oss.uploads == []


async def test_upload_errors_do_not_expose_sdk_exception_details(oss, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("private-credential-value")

    monkeypatch.setattr(oss, "put_object", fail)
    with pytest.raises(AppException, match="OSS 上传失败") as error:
        await OSSStorage.upload_bytes(b"image", "uploads/a.png")
    assert "private-credential-value" not in str(error.value)


async def test_object_existence_check_does_not_upload(oss):
    oss.existing.add("uploads/a.png")
    assert await OSSStorage.object_exists("uploads/a.png") is True
    assert await OSSStorage.object_exists("uploads/missing.png") is False
    assert oss.uploads == []


async def test_cached_images_upload_missing_objects_and_keep_existing_objects(oss, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    urls = []
    for index in range(1, 5):
        key = f"uploads/ai_images/old_{index}.png"
        path = tmp_path / f"ai_images/old_{index}.png"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(f"image-{index}".encode())
        urls.append(f"https://static.test/{key}")
    oss.existing.add("uploads/ai_images/old_1.png")
    await sync_generated_images(urls)
    assert [item[0] for item in oss.uploads] == [f"uploads/ai_images/old_{i}.png" for i in range(2, 5)]
    await sync_generated_images(urls)
    assert len(oss.uploads) == 3


async def test_missing_local_image_does_not_report_success(oss, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    with pytest.raises(AppException, match="本地文件不存在"):
        await sync_generated_images(["https://static.test/uploads/ai_images/missing.png"])
    assert oss.uploads == []


async def test_external_cached_urls_are_not_uploaded_to_owned_bucket(oss):
    await sync_generated_images(["https://other.test/uploads/ai_images/external.png"])
    assert oss.queries == []
    assert oss.uploads == []


@pytest.mark.parametrize("path", ["../secret.png", "%2e%2e/secret.png"])
async def test_cached_image_path_cannot_escape_upload_directory(oss, tmp_path, monkeypatch, path):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    with pytest.raises(AppException, match="路径格式错误"):
        await sync_generated_images([f"https://static.test/uploads/ai_images/{path}"])
    assert oss.queries == []
