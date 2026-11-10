"""
============================================
OSS Storage - shared asynchronous upload operations
============================================
Upload local files, bytes, or remote resources using backend environment credentials.
"""

import asyncio
import mimetypes
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import BinaryIO
from urllib.parse import quote, urlsplit

import httpx
import oss2
from anyio import to_thread

from app.common.exception import AppException
from app.core.config import settings
from app.pkg.logging import app_logger


class OSSStorage:
    """Share OSS uploads and public URL generation across business services."""

    @staticmethod
    def validate_config() -> None:
        """Fail before contacting upstream services if OSS configuration is incomplete."""
        required = ("OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_SECRET", "OSS_ENDPOINT", "OSS_BUCKET", "OSS_REGION", "OSS_VIEW_DOMAIN")
        missing = [name for name in required if not getattr(settings, name).strip()]
        if missing:
            raise AppException(msg="OSS 配置缺失：" + "、".join(missing))
        domain = urlsplit(settings.OSS_VIEW_DOMAIN)
        endpoint = urlsplit(OSSStorage._endpoint())
        if domain.scheme not in {"http", "https"} or not domain.netloc:
            raise AppException(msg="OSS_VIEW_DOMAIN 格式错误，请填写完整的访问域名")
        if endpoint.scheme not in {"http", "https"} or not endpoint.netloc or endpoint.path:
            raise AppException(msg="OSS_ENDPOINT 格式错误")

    @staticmethod
    def _endpoint() -> str:
        endpoint = settings.OSS_ENDPOINT.strip().rstrip("/")
        return endpoint if "://" in endpoint else f"https://{endpoint}"

    @staticmethod
    def _key(object_key: str) -> str:
        """Validate an object key while retaining its exact OSS path."""
        key = object_key.lstrip("/")
        if not key or "\\" in key or "\x00" in key or ".." in PurePosixPath(key).parts:
            raise AppException(msg="OSS 文件路径格式错误")
        return key

    @classmethod
    def get_url(cls, object_key: str) -> str:
        """Build a URL for a stored object without uploading it."""
        return f"{settings.OSS_VIEW_DOMAIN.rstrip('/')}/{quote(cls._key(object_key), safe='/~')}"

    @classmethod
    def _create_bucket(cls) -> oss2.Bucket:
        cls.validate_config()
        session = oss2.Session()
        session.session.trust_env = False
        return oss2.Bucket(
            oss2.AuthV4(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET),
            cls._endpoint(), settings.OSS_BUCKET,
            region=settings.OSS_REGION, session=session, connect_timeout=60,
        )

    @staticmethod
    def _storage_error(action: str, exc: Exception) -> AppException:
        # 不记录异常原文，避免 SDK 请求信息中包含认证数据。
        app_logger.error("OSS {}失败，code={} request_id={}", action,
                         getattr(exc, "code", type(exc).__name__), getattr(exc, "request_id", ""))
        return AppException(msg=f"OSS {action}失败，请检查存储配置和权限后重试")

    @classmethod
    async def upload_file(cls, file_path: str | Path, object_key: str, *, content_type: str | None = None) -> str:
        """Upload a local file and return its public URL after OSS acknowledges it."""
        cls.validate_config()
        key = cls._key(object_key)
        path = Path(file_path)
        if not await asyncio.to_thread(path.is_file):
            raise AppException(msg="待上传的文件不存在")
        mime = content_type or mimetypes.guess_type(key)[0] or "application/octet-stream"

        def upload():
            return cls._create_bucket().put_object_from_file(key, str(path), headers={"Content-Type": mime})

        try:
            result = await asyncio.to_thread(upload)
        except (oss2.exceptions.OssError, OSError, ValueError) as exc:
            raise cls._storage_error("上传", exc) from None
        if not 200 <= result.status < 300:
            raise AppException(msg="OSS 上传失败，请稍后重试")
        return cls.get_url(key)

    @classmethod
    async def upload_bytes(cls, content: bytes, object_key: str, *, content_type: str | None = None) -> str:
        """Upload in-memory content and return its public URL."""
        cls.validate_config()
        key = cls._key(object_key)
        mime = content_type or mimetypes.guess_type(key)[0] or "application/octet-stream"

        def upload():
            return cls._create_bucket().put_object(key, content, headers={"Content-Type": mime})

        try:
            result = await asyncio.to_thread(upload)
        except (oss2.exceptions.OssError, OSError, ValueError) as exc:
            raise cls._storage_error("上传", exc) from None
        if not 200 <= result.status < 300:
            raise AppException(msg="OSS 上传失败，请稍后重试")
        return cls.get_url(key)

    @classmethod
    async def upload_stream(cls, file: BinaryIO, object_key: str, *, content_type: str | None = None) -> str:
        """Upload a seekable file object in a worker thread without copying it into memory."""
        cls.validate_config()
        key = cls._key(object_key)
        mime = content_type or mimetypes.guess_type(key)[0] or "application/octet-stream"

        def upload():
            file.seek(0)
            return cls._create_bucket().put_object(key, file, headers={"Content-Type": mime})

        try:
            result = await to_thread.run_sync(upload)
        except (oss2.exceptions.OssError, OSError, ValueError) as exc:
            raise cls._storage_error("上传", exc) from None
        if not 200 <= result.status < 300:
            raise AppException(msg="OSS 上传失败，请稍后重试")
        return cls.get_url(key)

    @classmethod
    async def delete_object(cls, object_key: str) -> None:
        """Delete an object, including one whose attachment could not be persisted."""
        cls.validate_config()
        key = cls._key(object_key)
        try:
            result = await to_thread.run_sync(lambda: cls._create_bucket().delete_object(key))
        except (oss2.exceptions.OssError, OSError, ValueError) as exc:
            raise cls._storage_error("删除", exc) from None
        if not 200 <= result.status < 300:
            raise AppException(msg="OSS 删除失败，请稍后重试")

    @classmethod
    async def upload_url(cls, source_url: str, object_key: str, *, content_type: str | None = None, max_size: int | None = None) -> str:
        """Download a remote resource to a temporary file and upload it to OSS."""
        cls.validate_config()
        key = cls._key(object_key)
        limit = max_size if max_size is not None else settings.FILE_VIDEO_MAX_SIZE
        with TemporaryDirectory(prefix="oss-upload-") as directory:
            path = Path(directory) / "resource"
            try:
                async with httpx.AsyncClient(timeout=120, trust_env=False, follow_redirects=True) as client:
                    async with client.stream("GET", source_url) as response:
                        response.raise_for_status()
                        mime = content_type or response.headers.get("Content-Type", "").split(";", 1)[0] or None
                        size = 0
                        with path.open("wb") as output:
                            async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                                size += len(chunk)
                                if size > limit:
                                    raise AppException(msg="远程文件大小超过上传限制")
                                await asyncio.to_thread(output.write, chunk)
            except httpx.HTTPError:
                raise AppException(msg="远程文件下载失败，请稍后重试") from None
            return await cls.upload_file(path, key, content_type=mime)

    @classmethod
    async def object_exists(cls, object_key: str) -> bool:
        """Check an object's existence without downloading its contents."""
        cls.validate_config()
        key = cls._key(object_key)
        try:
            return await asyncio.to_thread(lambda: cls._create_bucket().object_exists(key))
        except (oss2.exceptions.OssError, OSError, ValueError) as exc:
            raise cls._storage_error("查询", exc) from None
