"""
============================================
AI Image Service - PHP image generation workflow
============================================
Ports AiLogic.php toImage/getTask/getImage into asynchronous Python services.
"""

from typing import Any, NoReturn

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.constants.ai import FAILED_TASK_STATUSES, PENDING_TASK_STATUSES, TaskStatus
from app.core.config import settings
from app.models.ai_to_work import AiToWork
from app.pkg.qwen_client import QwenTaskClient
from app.schemas.ai import ImageRequest
from app.services.ai_task_service import extract_task_error, fail_task, load_task_work
from app.storage.ai_image import save_generated_image, sync_generated_images
from app.storage.oss import OSSStorage


class AIImageService:
    """Submit image tasks and retrieve owned, persisted generation results."""

    IMAGE_MODELS = {1: "wanx2.1-t2i-turbo", 2: "wanx2.1-t2i-plus"}

    @classmethod
    async def to_image(cls, db: AsyncSession, req: ImageRequest, user_id: int) -> str:
        """Submit an image task and persist its parameters, returning the task ID."""
        if settings.OSS_ENABLED:
            OSSStorage.validate_config()
        # 对应 PHP toImage：异步提交后只保存任务，不在请求中等待图片生成。
        data = await QwenTaskClient.request(
            "POST",
            settings.QWEN_IMAGE_URL,
            media_type="图片",
            payload={
                "model": cls.IMAGE_MODELS[req.model],
                "input": {"prompt": req.prompt},
                "parameters": {
                    "size": f"{req.size[0]}*{req.size[1]}",
                    "n": req.n,
                    # 与 PHP toImage 一致，由千问处理默认水印。
                    "watermark": req.watermark == 1,
                },
            },
        )
        output = data.get("output") or {}
        task_id = output.get("task_id")
        if not isinstance(task_id, str) or not task_id or len(task_id) > 255:
            raise AppException(msg="图片生成失败，" + str(data.get("message") or "未返回任务 ID"))
        task = AiToWork(
            user_id=user_id,
            task_id=task_id,
            params=req.model_dump(mode="json"),
            type=1,
            status=TaskStatus.GENERATING,
            work=None,
        )
        db.add(task)
        await db.commit()
        return task_id

    @classmethod
    async def get_image(
        cls, db: AsyncSession, task_id: str, user_id: int
    ) -> dict[str, list[str]] | str:
        """Return cached image URLs, or the task ID while generation is pending."""
        task = await cls._get_task(db, task_id, user_id)
        cached = await cls._try_get_cached_result(task)
        if cached is not None:
            return cached

        data = await QwenTaskClient.get_task(task_id, media_type="图片")
        return await cls._handle_upstream_status(db, task, data["output"])

    @staticmethod
    async def _get_task(db: AsyncSession, task_id: str, user_id: int) -> AiToWork:
        """Find an image task owned by the current user."""
        result = await db.execute(
            select(AiToWork).where(
                AiToWork.task_id == task_id,
                AiToWork.user_id == user_id,
                AiToWork.type == 1,
            )
        )
        task = result.scalar_one_or_none()
        if task is None:
            raise AppException(msg="任务不存在")
        return task

    @classmethod
    async def _try_get_cached_result(cls, task: AiToWork) -> dict[str, list[str]] | None:
        """Return repaired cached images or raise a stored terminal error."""
        if task.status == TaskStatus.DELETED:
            raise AppException(msg="任务不存在")
        if task.status not in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            return None

        work = load_task_work(task.work, media_type="图片")
        if not isinstance(work, (list, dict)):
            raise AppException(msg="图片任务记录格式错误")
        if task.status == TaskStatus.FAILED:
            message = extract_task_error(work, default="服务错误，请稍后再试")
            raise AppException(msg=f"图片生成失败，{message}")

        images = cls._format_result(work)
        # 历史缓存可能只有本地图片，命中缓存时仍需检查并补传 OSS。
        await sync_generated_images(images["image"])
        return images

    @classmethod
    async def _handle_upstream_status(
        cls, db: AsyncSession, task: AiToWork, output: dict[str, Any]
    ) -> dict[str, list[str]] | str:
        """Route an upstream task state to its business operation."""
        status = output.get("task_status")
        if status in PENDING_TASK_STATUSES:
            return task.task_id
        if status == "SUCCEEDED":
            return await cls._handle_success(db, task, output)
        if status in FAILED_TASK_STATUSES:
            await cls._handle_failure(db, task, output)
        # 网络错误或不完整响应不应把仍在运行的任务永久标记为失败。
        raise AppException(msg="图片任务查询失败，请稍后重试")

    @classmethod
    async def _handle_success(
        cls, db: AsyncSession, task: AiToWork, output: dict[str, Any]
    ) -> dict[str, list[str]]:
        """Download and upload every image before committing the completed task."""
        urls: list[str] = []
        for index, item in enumerate(output.get("results") or [], start=1):
            if not isinstance(item, dict) or not item.get("url"):
                continue
            path = await save_generated_image(item["url"], task.task_id, index)
            urls.append(f"/uploads/{path}")
        if not urls:
            await fail_task(db, task, "未返回可用图片", media_type="图片")

        # save_generated_image 已完成 OSS 上传，全部保存成功后才更新任务。
        result = cls._format_result(urls)
        task.work = result["image"]
        task.status = TaskStatus.COMPLETED
        await db.commit()
        return result

    @staticmethod
    async def _handle_failure(
        db: AsyncSession, task: AiToWork, output: dict[str, Any]
    ) -> NoReturn:
        """Translate and persist a terminal upstream failure."""
        if output.get("task_status") == "UNKNOWN":
            message = "任务不存在"
        elif output.get("code"):
            message = QwenTaskClient.error_message(output["code"], media_type="图片")
        else:
            message = str(output.get("message") or "任务已取消或生成失败")
        await fail_task(db, task, message, media_type="图片")

    @staticmethod
    def _format_result(urls: object) -> dict[str, list[str]]:
        """Return image URLs under the image field."""
        if not isinstance(urls, list) or not all(isinstance(url, str) for url in urls):
            raise AppException(msg="图片任务记录格式错误")
        # 历史任务可能缓存相对路径，返回时补齐当前配置的文件访问域名。
        prefix = (settings.OSS_VIEW_DOMAIN if settings.OSS_ENABLED else settings.FILE_BASE_URL).rstrip("/")
        if prefix:
            urls = [f"{prefix}{url}" if url.startswith("/uploads/") else url for url in urls]
        return {"image": urls}
