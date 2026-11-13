"""
============================================
AI 视频存储 - 下载、水印、OSS 上传与本地文件清理
============================================
复用 PHP 的 FFmpeg 水印流程，发布生成视频并在业务确认成功后清理本地成片。
"""

import asyncio
import shutil
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote, urlsplit

import httpx

from app.common.exception import AppException
from app.core.config import settings
from app.pkg.logging import app_logger
from app.storage.oss import OSSStorage


async def validate_video_storage() -> None:
    """Check watermark and FFmpeg availability before submitting a paid task."""
    if not await asyncio.to_thread(shutil.which, settings.FFMPEG_BIN):
        raise AppException(msg="FFmpeg 未安装或 FFMPEG_BIN 配置错误")
    if not await asyncio.to_thread(Path(settings.AI_VIDEO_WATERMARK_PATH).is_file):
        raise AppException(msg="视频水印文件不存在，请检查 AI_VIDEO_WATERMARK_PATH")
    if settings.OSS_ENABLED:
        OSSStorage.validate_config()
        domain = urlsplit(settings.AI_VIDEO_BASE_URL)
        if domain.scheme not in {"http", "https"} or not domain.netloc or domain.query or domain.fragment:
            raise AppException(msg="AI_VIDEO_BASE_URL 格式错误，请填写完整的视频访问域名")
    if settings.AI_VIDEO_FFMPEG_TIMEOUT <= 0:
        raise AppException(msg="AI_VIDEO_FFMPEG_TIMEOUT 必须大于 0")


def get_video_url(object_key: str) -> str:
    """Build a video URL using the independent video delivery domain."""
    prefix = settings.AI_VIDEO_BASE_URL if settings.OSS_ENABLED else settings.FILE_BASE_URL
    return f"{prefix.rstrip('/')}/{quote(object_key, safe='/~')}"


async def _download_video(url: str, destination: Path) -> None:
    """Stream a generated video to disk with the configured size limit."""
    try:
        async with httpx.AsyncClient(timeout=120.0, trust_env=False, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                size = 0
                with destination.open("wb") as output:
                    async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                        size += len(chunk)
                        if size > settings.FILE_VIDEO_MAX_SIZE:
                            raise AppException(msg="生成视频大小超过存储限制")
                        await asyncio.to_thread(output.write, chunk)
                if size == 0:
                    raise AppException(msg="生成视频内容为空")
    except httpx.HTTPError as exc:
        raise AppException(msg="生成视频下载失败，请稍后重试") from exc


async def add_video_watermark(input_path: Path, output_path: Path) -> None:
    """Overlay the original PNG ten pixels from the right and bottom edges."""
    # 与 PHP 使用同一 overlay 表达式；逐项传参可兼容带空格的路径。
    try:
        process = await asyncio.create_subprocess_exec(
            settings.FFMPEG_BIN,
            "-nostdin", "-y", "-loglevel", "error",
            "-i", str(input_path),
            "-i", str(Path(settings.AI_VIDEO_WATERMARK_PATH).resolve()),
            "-filter_complex", "overlay=W-w-10:H-h-10",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-movflags", "+faststart",
            str(output_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise AppException(msg="FFmpeg 启动失败，请检查运行环境") from exc

    try:
        _, stderr = await asyncio.wait_for(
            process.communicate(), timeout=settings.AI_VIDEO_FFMPEG_TIMEOUT
        )
    except (TimeoutError, asyncio.CancelledError) as exc:
        # 超时或请求取消时必须终止子进程，再清理临时文件。
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        await process.communicate()
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise AppException(msg="视频水印处理超时，请稍后重试") from exc

    if process.returncode != 0:
        app_logger.warning(
            "视频水印处理失败，code={} detail={}",
            process.returncode, stderr.decode(errors="replace")[-1000:],
        )
        raise AppException(msg="视频水印添加失败，请稍后重试")
    if not await asyncio.to_thread(output_path.is_file):
        raise AppException(msg="视频水印处理未生成文件")
    size = (await asyncio.to_thread(output_path.stat)).st_size
    if size == 0 or size > settings.FILE_VIDEO_MAX_SIZE:
        raise AppException(msg="水印视频为空或大小超过存储限制")


async def save_generated_video(url: str, task_id: str) -> str:
    """下载、加水印并上传视频，返回访问地址；成片待业务提交成功后清理。"""
    await validate_video_storage()
    safe_id = uuid.uuid5(uuid.NAMESPACE_URL, task_id).hex
    relative_path = f"ai_videos/{safe_id}.mp4"
    root = Path(settings.UPLOAD_DIR)
    file_path = root / relative_path
    await asyncio.to_thread(file_path.parent.mkdir, parents=True, exist_ok=True)

    # 上传失败时保留已经加水印的成片，下次查询只需重试上传。
    if not await asyncio.to_thread(file_path.is_file):
        temporary_root = root / "temp"
        await asyncio.to_thread(temporary_root.mkdir, parents=True, exist_ok=True)
        try:
            with TemporaryDirectory(prefix=f"{safe_id}_", dir=temporary_root) as directory:
                input_path = Path(directory) / "input.mp4"
                output_path = Path(directory) / "output.mp4"
                await _download_video(url, input_path)
                await add_video_watermark(input_path, output_path)
                await asyncio.to_thread(output_path.replace, file_path)
        except OSError as exc:
            raise AppException(msg="视频文件保存失败，请检查存储目录后重试") from exc

    if settings.OSS_ENABLED:
        # 上传得到确认后才能由业务层保存 status=1，避免返回不存在的 OSS 地址。
        await OSSStorage.upload_file(
            file_path, f"uploads/{relative_path}", content_type="video/mp4"
        )
    return get_video_url(f"uploads/{relative_path}")


async def cleanup_generated_video(task_id: str) -> None:
    """OSS 上传及数据库提交成功后清理成片；本地存储模式保留文件。"""
    if not settings.OSS_ENABLED:
        return
    safe_id = uuid.uuid5(uuid.NAMESPACE_URL, task_id).hex
    file_path = Path(settings.UPLOAD_DIR) / "ai_videos" / f"{safe_id}.mp4"
    try:
        await asyncio.to_thread(file_path.unlink, missing_ok=True)
    except OSError as exc:
        # 任务已成功入库，清理异常只记录日志，不影响已发布的视频结果。
        app_logger.warning("视频已生成，本地成片清理失败，task_id={} error={}", task_id, exc)
