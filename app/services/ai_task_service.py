"""
============================================
AI Task Helpers - shared result and failure handling
============================================
Decode stored task results and persist terminal failures for image and video tasks.
"""

import json
from typing import NoReturn

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.constants.ai import TaskStatus
from app.models.ai_to_work import AiToWork
from app.pkg.qwen_client import TaskMediaType


def load_task_work(work: object, *, media_type: TaskMediaType) -> object:
    """Decode legacy JSON strings while preserving native JSON column values."""
    if not isinstance(work, str):
        return work
    try:
        return json.loads(work)
    except json.JSONDecodeError as exc:
        raise AppException(msg=f"{media_type}任务记录格式错误") from exc


def extract_task_error(work: object, *, default: str) -> str:
    """Read a cached error with a fallback for missing or empty messages."""
    if isinstance(work, dict):
        return str(work.get("error") or default)
    return default


async def fail_task(
    db: AsyncSession,
    task: AiToWork,
    message: str,
    *,
    media_type: TaskMediaType,
) -> NoReturn:
    """Commit a terminal failure before raising its business exception."""
    task.work = {"error": message}
    task.status = TaskStatus.FAILED
    # 先提交失败结果，再抛异常；后续请求可直接读取失败记录。
    await db.commit()
    raise AppException(msg=f"{media_type}生成失败，{message}")
