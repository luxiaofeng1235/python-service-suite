"""
============================================
AI Image Service - PHP image generation workflow
============================================
Ports AiLogic.php toImage/getTask/getImage into asynchronous Python services.
"""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.core.config import settings
from app.models.ai_to_work import AiToWork
from app.pkg.qwen_client import QwenTaskClient
from app.schemas.ai import ImageRequest
from app.storage.ai_image import save_generated_image, sync_generated_images
from app.storage.oss import OSSStorage


class AIImageService:
    """Submit image tasks and retrieve owned, persisted generation results."""

    IMAGE_MODELS = {1: "wanx2.1-t2i-turbo", 2: "wanx2.1-t2i-plus"}
    PENDING_STATUSES = {"PENDING", "RUNNING", "SUSPENDED"}

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
            status=0,
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
        # 对应 PHP getTask：必须先校验归属；已完成的任务直接读取数据库缓存。
        result = await db.execute(
            select(AiToWork).where(
                AiToWork.task_id == task_id,
                AiToWork.user_id == user_id,
                AiToWork.type == 1,
            )
        )
        task = result.scalar_one_or_none()
        # status=3 表示已删除，不再查询上游或返回历史作品。
        if task is None or task.status == 3:
            raise AppException(msg="任务不存在")
        if task.status == 1:
            images = cls._image_result(cls._load_work(task.work))
            await sync_generated_images(images["image"])
            return images
        if task.status == 2:
            work = cls._load_work(task.work)
            message = "服务错误，请稍后再试"
            if isinstance(work, dict):
                message = work.get("error") or message
            raise AppException(msg=f"图片生成失败，{message}")

        data = await QwenTaskClient.get_task(task_id, media_type="图片")
        output = data.get("output") or {}
        status = output.get("task_status")
        if status in cls.PENDING_STATUSES:
            return task_id
        if status == "SUCCEEDED":
            # 对应 PHP getImage：先下载图片，再保存地址，后续查询不再请求上游。
            urls: list[str] = []
            for index, item in enumerate(output.get("results") or [], start=1):
                if not isinstance(item, dict) or not item.get("url"):
                    continue
                path = await save_generated_image(item["url"], task_id, index)
                urls.append(f"/uploads/{path}")
            if not urls:
                await cls._fail_task(db, task, "未返回可用图片")
            urls = cls._image_result(urls)["image"]
            task.work = urls
            task.status = 1
            await db.commit()
            return cls._image_result(urls)
        if status in {"FAILED", "CANCELED", "UNKNOWN"}:
            if status == "UNKNOWN":
                message = "任务不存在"
            elif output.get("code"):
                message = QwenTaskClient.error_message(output["code"], media_type="图片")
            else:
                message = str(output.get("message") or "任务已取消或生成失败")
            await cls._fail_task(db, task, message)
        # 网络错误或不完整响应不应把仍在运行的任务永久标记为失败。
        raise AppException(msg="图片任务查询失败，请稍后重试")

    @staticmethod
    async def _fail_task(db: AsyncSession, task: AiToWork, message: str) -> None:
        """Persist a terminal task failure before raising a business exception."""
        task.work = {"error": message}
        task.status = 2
        await db.commit()
        raise AppException(msg=f"图片生成失败，{message}")

    @staticmethod
    def _load_work(work: Any) -> list[str] | dict[str, Any]:
        """Accept JSON columns and legacy JSON-encoded strings."""
        if isinstance(work, str):
            try:
                work = json.loads(work)
            except json.JSONDecodeError as exc:
                raise AppException(msg="图片任务记录格式错误") from exc
        if not isinstance(work, (list, dict)):
            raise AppException(msg="图片任务记录格式错误")
        return work

    @staticmethod
    def _image_result(urls: list[str] | dict[str, Any]) -> dict[str, list[str]]:
        """Return image URLs under the image field."""
        if not isinstance(urls, list) or not all(isinstance(url, str) for url in urls):
            raise AppException(msg="图片任务记录格式错误")
        # 历史任务可能缓存相对路径，返回时补齐当前配置的文件访问域名。
        prefix = (settings.OSS_VIEW_DOMAIN if settings.OSS_ENABLED else settings.FILE_BASE_URL).rstrip("/")
        if prefix:
            urls = [f"{prefix}{url}" if url.startswith("/uploads/") else url for url in urls]
        return {"image": urls}
