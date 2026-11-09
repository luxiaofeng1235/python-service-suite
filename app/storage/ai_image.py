"""
============================================
AI Image Storage - generated image downloads
============================================
Downloads generated images and optionally applies the platform PNG watermark.
"""

import asyncio
import uuid
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

import httpx
from PIL import Image, ImageOps

from app.common.exception import AppException
from app.core.config import settings
from app.storage.oss import OSSStorage


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WATERMARK_WIDTH_RATIO = 0.25
WATERMARK_MARGIN_RATIO = 0.02


def _apply_watermark(image_path: Path) -> None:
    """Composite the configured PNG at the bottom right and save a PNG image."""
    watermark_path = Path(settings.AI_IMAGE_WATERMARK_PATH)
    if not watermark_path.is_absolute():
        watermark_path = PROJECT_ROOT / watermark_path
    if not watermark_path.is_file():
        raise AppException(msg="水印文件不存在，请检查水印配置")
    try:
        with Image.open(image_path) as source, Image.open(watermark_path) as mark_source:
            image = ImageOps.exif_transpose(source).convert("RGBA")
            mark = mark_source.convert("RGBA")
            margin = max(1, round(min(image.size) * WATERMARK_MARGIN_RATIO))
            max_width = max(1, min(image.width - 2 * margin, round(image.width * WATERMARK_WIDTH_RATIO)))
            max_height = max(1, image.height - 2 * margin)
            mark.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            x = max(0, image.width - mark.width - margin)
            y = max(0, image.height - mark.height - margin)
            # 保留 PNG 的透明通道；轻微阴影使白色水印在浅色图片上仍可辨认。
            shadow = Image.new("RGBA", mark.size, (0, 0, 0, 0))
            shadow.putalpha(mark.getchannel("A"))
            image.alpha_composite(shadow, (min(x + 1, image.width - mark.width),
                                           min(y + 1, image.height - mark.height)))
            image.alpha_composite(mark, (x, y))
            image.save(image_path, format="PNG")
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise AppException(msg="图片水印处理失败，请检查原图和水印文件") from exc


async def save_generated_image(
    url: str, task_id: str, index: int, *, watermark: bool = False
) -> str:
    """Download an image, optionally watermark it, and return its upload path."""
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
                        if size > settings.FILE_IMAGE_MAX_SIZE:
                            raise AppException(msg="生成图片大小超过存储限制")
                        await asyncio.to_thread(output.write, chunk)
                if size == 0:
                    raise AppException(msg="生成图片内容为空")
        if watermark:
            # 图片解码和合成在线程中执行，完成后才将临时文件替换为正式文件。
            await asyncio.to_thread(_apply_watermark, temporary_path)
            if await asyncio.to_thread(lambda: temporary_path.stat().st_size > settings.FILE_IMAGE_MAX_SIZE):
                raise AppException(msg="加水印后的图片大小超过存储限制")
        await asyncio.to_thread(temporary_path.replace, file_path)
    except httpx.HTTPError as exc:
        raise AppException(msg="生成图片下载失败，请稍后重试") from exc
    finally:
        await asyncio.to_thread(temporary_path.unlink, missing_ok=True)
    if settings.OSS_ENABLED:
        # 必须先完成水印处理和 OSS 上传，业务层才能将任务标记为成功。
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
