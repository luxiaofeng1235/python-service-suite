"""
============================================
AI Video Service - text-to-video tasks and result persistence
============================================
Port PHP toVideo/getVideo with ownership checks and serialized local processing.
"""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.core.config import settings
from app.models.ai_to_work import AiToWork
from app.pkg.qwen_client import QwenTaskClient
from app.schemas.ai import VideoRequest
from app.storage.ai_video import get_video_url, save_generated_video, validate_video_storage


class AIVideoService:
    """Submit text-to-video tasks and persist watermarked video URLs."""

    VIDEO_MODEL = "wanx2.1-t2v-turbo"
    PENDING_STATUSES = {"PENDING", "RUNNING", "SUSPENDED"}

    @classmethod
    async def to_video(cls, db: AsyncSession, req: VideoRequest, user_id: int) -> str:
        """Submit the PHP to=2 text-to-video model and save its task ID."""
        await validate_video_storage()
        data = await QwenTaskClient.request(
            "POST", settings.QWEN_VIDEO_URL,
            media_type="视频",
            payload={"model": cls.VIDEO_MODEL, "input": {"prompt": req.prompt}},
        )
        task_id = data["output"].get("task_id")
        if not isinstance(task_id, str) or not task_id or len(task_id) > 255:
            raise AppException(msg="视频生成失败，未返回有效任务 ID")
        db.add(AiToWork(
            user_id=user_id, task_id=task_id, params=req.model_dump(mode="json"),
            type=2, status=0, work=None,
        ))
        await db.commit()
        return task_id

    @classmethod
    async def get_video(
        cls, db: AsyncSession, task_id: str, user_id: int
    ) -> dict[str, list[str]] | str:
        """Return progress or publish the owned task after watermarking it."""
        stmt = select(AiToWork).where(
            AiToWork.task_id == task_id,
            AiToWork.user_id == user_id,
            AiToWork.type == 2,
        )
        task = (await db.execute(stmt)).scalar_one_or_none()
        if task is None:
            raise AppException(msg="任务不存在")
        cached = cls._cached_result(task)
        if cached is not None:
            return cached
        await db.commit()

        # MySQL 8 行锁覆盖查询、下载、转码和上传；其他轮询直接返回生成中。
        # status=3 始终只表示已删除，不借用它表示水印处理中。
        try:
            task = (await db.execute(
                stmt.with_for_update(skip_locked=True).execution_options(populate_existing=True)
            )).scalar_one_or_none()
            if task is None:
                await db.rollback()
                return task_id
            cached = cls._cached_result(task)
            if cached is not None:
                await db.commit()
                return cached
            data = await QwenTaskClient.get_task(task_id, media_type="视频")
            output = data["output"]
            status = output.get("task_status")
            if status in cls.PENDING_STATUSES:
                await db.commit()
                return task_id
            if status == "SUCCEEDED":
                video_url = output.get("video_url")
                if not video_url and isinstance(output.get("results"), dict):
                    video_url = output["results"].get("video_url")
                if not isinstance(video_url, str) or not video_url:
                    raise AppException(msg="视频任务未返回可用视频，请稍后重试")
                url = await save_generated_video(video_url, task_id)
                task.work = [url]
                task.status = 1
                await db.commit()
                return {"video": [url]}
            if status in {"FAILED", "CANCELED", "UNKNOWN"}:
                message = (
                    "任务不存在或已过期" if status == "UNKNOWN"
                    else QwenTaskClient.error_message(output.get("code"), media_type="视频")
                )
                task.work = {"error": message}
                task.status = 2
                await db.commit()
                raise AppException(msg=f"视频生成失败，{message}")
            raise AppException(msg="视频任务查询失败，请稍后重试")
        except BaseException:
            # 下载、FFmpeg、OSS 或请求取消均释放行锁，保留待处理状态以便重试。
            await db.rollback()
            raise

    @staticmethod
    def _cached_result(task: AiToWork) -> dict[str, list[str]] | None:
        """Read completed or failed results, accepting legacy JSON strings."""
        if task.status == 3:
            raise AppException(msg="任务不存在")
        if task.status not in {1, 2}:
            return None
        work: Any = task.work
        if isinstance(work, str):
            try:
                work = json.loads(work)
            except json.JSONDecodeError as exc:
                raise AppException(msg="视频任务记录格式错误") from exc
        if task.status == 2:
            message = work.get("error") if isinstance(work, dict) else None
            raise AppException(msg=f"视频生成失败，{message or '服务错误，请稍后重试'}")
        if not isinstance(work, list) or not work or not all(isinstance(url, str) for url in work):
            raise AppException(msg="视频任务记录格式错误")
        return {"video": [get_video_url(url.lstrip("/")) if url.startswith("/uploads/") else url for url in work]}
