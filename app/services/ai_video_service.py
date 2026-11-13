"""
============================================
AI 视频服务 - 文生视频任务与作品持久化
============================================
沿用 PHP toVideo/getVideo，校验任务归属、串行处理视频并在保存成功后清理本地成片。
"""

from typing import Any, NoReturn

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.constants.ai import FAILED_TASK_STATUSES, PENDING_TASK_STATUSES, TaskStatus
from app.core.config import settings
from app.models.ai_to_work import AiToWork
from app.pkg.qwen_client import QwenTaskClient
from app.schemas.ai import VideoRequest
from app.services.ai_task_service import extract_task_error, fail_task, load_task_work
from app.storage.ai_video import (
    cleanup_generated_video,
    get_video_url,
    save_generated_video,
    validate_video_storage,
)


class AIVideoService:
    """Submit text-to-video tasks and persist watermarked video URLs."""

    VIDEO_MODEL = "wanx2.1-t2v-turbo"

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
            type=2, status=TaskStatus.GENERATING, work=None,
        ))
        await db.commit()
        return task_id

    @classmethod
    async def get_video(
        cls, db: AsyncSession, task_id: str, user_id: int
    ) -> dict[str, list[str]] | str:
        """Return progress or publish the owned task after watermarking it."""
        task = await cls._get_task(db, task_id, user_id)
        cached = cls._try_get_cached_result(task)
        if cached is not None:
            return cached
        # 结束首次查询的事务，再进入行锁保护的处理流程。
        await db.commit()
        return await cls._get_locked_result(db, task_id, user_id)

    @staticmethod
    def _task_query(task_id: str, user_id: int) -> Select[tuple[AiToWork]]:
        """Build the same ownership filter for ordinary and locked reads."""
        return select(AiToWork).where(
            AiToWork.task_id == task_id,
            AiToWork.user_id == user_id,
            AiToWork.type == 2,
        )

    @classmethod
    async def _get_task(cls, db: AsyncSession, task_id: str, user_id: int) -> AiToWork:
        """Find a video task owned by the current user."""
        task = (await db.execute(cls._task_query(task_id, user_id))).scalar_one_or_none()
        if task is None:
            raise AppException(msg="任务不存在")
        return task

    @classmethod
    async def _get_locked_result(
        cls, db: AsyncSession, task_id: str, user_id: int
    ) -> dict[str, list[str]] | str:
        """Serialize video processing and release the lock on every exit path."""
        # MySQL 8 行锁覆盖查询、下载、转码和上传；其他轮询直接返回生成中。
        # status=3 始终只表示已删除，不借用它表示水印处理中。
        stmt = cls._task_query(task_id, user_id).with_for_update(skip_locked=True)
        stmt = stmt.execution_options(populate_existing=True)
        try:
            task = (await db.execute(stmt)).scalar_one_or_none()
            if task is None:
                await db.rollback()
                return task_id
            # 获取锁前任务可能已被其他请求处理，必须重新检查缓存。
            cached = cls._try_get_cached_result(task)
            if cached is not None:
                await db.commit()
                return cached
            data = await QwenTaskClient.get_task(task_id, media_type="视频")
            return await cls._handle_upstream_status(db, task, data["output"])
        except BaseException:
            # 下载、FFmpeg、OSS 或请求取消均释放行锁，保留待处理状态以便重试。
            await db.rollback()
            raise

    @classmethod
    async def _handle_upstream_status(
        cls, db: AsyncSession, task: AiToWork, output: dict[str, Any]
    ) -> dict[str, list[str]] | str:
        """Route upstream states while retaining the processing transaction."""
        status = output.get("task_status")
        if status in PENDING_TASK_STATUSES:
            await db.commit()
            return task.task_id
        if status == "SUCCEEDED":
            return await cls._handle_success(db, task, output)
        if status in FAILED_TASK_STATUSES:
            await cls._handle_failure(db, task, output)
        raise AppException(msg="视频任务查询失败，请稍后重试")

    @staticmethod
    async def _handle_success(
        db: AsyncSession, task: AiToWork, output: dict[str, Any]
    ) -> dict[str, list[str]]:
        """下载、加水印并上传视频，提交成功后清理本地成片。"""
        video_url = output.get("video_url")
        if not video_url and isinstance(output.get("results"), dict):
            video_url = output["results"].get("video_url")
        if not isinstance(video_url, str) or not video_url:
            raise AppException(msg="视频任务未返回可用视频，请稍后重试")

        url = await save_generated_video(video_url, task.task_id)
        task.work = [url]
        task.status = TaskStatus.COMPLETED
        await db.commit()
        # 与 PHP 一致，上传和入库均成功后再删除；失败时保留成片供下次重试。
        await cleanup_generated_video(task.task_id)
        return {"video": [url]}

    @staticmethod
    async def _handle_failure(
        db: AsyncSession, task: AiToWork, output: dict[str, Any]
    ) -> NoReturn:
        """Translate and persist a terminal upstream failure."""
        message = (
            "任务不存在或已过期" if output.get("task_status") == "UNKNOWN"
            else QwenTaskClient.error_message(output.get("code"), media_type="视频")
        )
        await fail_task(db, task, message, media_type="视频")

    @classmethod
    def _try_get_cached_result(cls, task: AiToWork) -> dict[str, list[str]] | None:
        """Read completed or failed results, accepting legacy JSON strings."""
        if task.status == TaskStatus.DELETED:
            raise AppException(msg="任务不存在")
        if task.status not in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            return None

        work = load_task_work(task.work, media_type="视频")
        if task.status == TaskStatus.FAILED:
            message = extract_task_error(work, default="服务错误，请稍后重试")
            raise AppException(msg=f"视频生成失败，{message}")
        return cls._format_result(work)

    @staticmethod
    def _format_result(work: object) -> dict[str, list[str]]:
        """Validate cached video URLs and normalize legacy local paths."""
        if not isinstance(work, list) or not work or not all(isinstance(url, str) for url in work):
            raise AppException(msg="视频任务记录格式错误")
        urls = [
            get_video_url(url.lstrip("/")) if url.startswith("/uploads/") else url
            for url in work
        ]
        return {"video": urls}
