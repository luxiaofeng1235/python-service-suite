"""
============================================
AI 图片存储 - 生成图片下载与 OSS 同步
============================================
原样下载生成图片，按配置上传 OSS，并补传历史任务缺失的文件。
"""

import asyncio
import uuid
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

import httpx

from app.common.exception import AppException
from app.core.config import settings
from app.storage.oss import OSSStorage


async def save_generated_image(url: str, task_id: str, index: int) -> str:
    """按 AI 图片独立大小上限下载原图并返回上传路径。"""
    # 文件名使用任务 ID 的安全形式，避免上游任务标识影响本地目录。
    safe_id = uuid.uuid5(uuid.NAMESPACE_URL, task_id).hex
    relative_path = f"ai_images/{safe_id}_{index}.png"
    file_path = Path(settings.UPLOAD_DIR) / relative_path
    temporary_path = file_path.with_name(f"{file_path.name}.{uuid.uuid4().hex}.tmp")
    await asyncio.to_thread(file_path.parent.mkdir, parents=True, exist_ok=True)
    try:
        async with httpx.AsyncClient(timeout=120.0, trust_env=False, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                size = 0
                with temporary_path.open("wb") as output:
                    async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                        size += len(chunk)
                        if size > settings.AI_IMAGE_MAX_SIZE:
                            raise AppException(msg="生成图片大小超过存储限制")
                        await asyncio.to_thread(output.write, chunk)
                if size == 0:
                    raise AppException(msg="生成图片内容为空")
        await asyncio.to_thread(temporary_path.replace, file_path)
    except httpx.HTTPError as exc:
        raise AppException(msg="生成图片下载失败，请稍后重试") from exc
    finally:
        await asyncio.to_thread(temporary_path.unlink, missing_ok=True)
    if settings.OSS_ENABLED:
        # 必须先完成 OSS 上传，业务层才能将任务标记为成功。
        await OSSStorage.upload_file(file_path, f"uploads/{relative_path}", content_type="image/png")
    return relative_path


async def sync_generated_images(urls: list[str]) -> None:
    """Repair cached local-only images without regenerating them or overwriting OSS objects."""
    if not settings.OSS_ENABLED:
        return
    allowed_hosts = {urlsplit(settings.OSS_VIEW_DOMAIN).netloc, urlsplit(settings.FILE_BASE_URL).netloc}
    root = Path(settings.UPLOAD_DIR).resolve()
    for url in urls:
        parsed = urlsplit(url)
        if parsed.netloc and parsed.netloc not in allowed_hosts:
            continue
        path = unquote(parsed.path)
        if not path.startswith("/uploads/ai_images/"):
            continue
        relative = path.removeprefix("/uploads/")
        if ".." in PurePosixPath(relative).parts or "\\" in relative:
            raise AppException(msg="图片文件路径格式错误")
        local_path = (root / relative).resolve()
        if not local_path.is_relative_to(root):
            raise AppException(msg="图片文件路径格式错误")
        key = f"uploads/{relative}"
        if await OSSStorage.object_exists(key):
            continue
        if not await asyncio.to_thread(local_path.is_file):
            raise AppException(msg="图片未上传到 OSS，且本地文件不存在，无法补传")
        await OSSStorage.upload_file(local_path, key, content_type="image/png")
