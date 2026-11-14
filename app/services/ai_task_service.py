"""
============================================
AI 任务公共方法 - 结果读取与失败处理
============================================
统一读取图片和视频任务的已保存结果，并持久化生成失败状态。
"""

import json
from typing import NoReturn

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.constants.ai import TaskStatus
from app.models.ai_to_work import AiToWork
from app.pkg.qwen_client import TaskMediaType


def load_task_work(work: object, *, media_type: TaskMediaType) -> object:
    """兼容历史 JSON 字符串，保留 JSON 字段原有的数据结构。"""
    if not isinstance(work, str):
        return work
    try:
        return json.loads(work)
    except json.JSONDecodeError as exc:
        raise AppException(msg=f"{media_type}任务记录格式错误") from exc


def extract_task_error(work: object, *, default: str) -> str:
    """读取已保存的错误信息，缺失或为空时使用默认提示。"""
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
    """先提交任务失败状态，再抛出业务异常。"""
    task.work = {"error": message}
    task.status = TaskStatus.FAILED
    # 先提交失败结果，再抛异常；后续请求可直接读取失败记录。
    await db.commit()
    raise AppException(msg=f"{media_type}生成失败，{message}")
