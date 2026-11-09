"""
============================================
AI 任务常量 - 生成任务状态
============================================
数据库任务状态与千问上游状态分别维护。
"""

from enum import IntEnum


class TaskStatus(IntEnum):
    """对应 ai_to_work 表的 status 字段，沿用现有数据库数值。"""

    GENERATING = 0  # 生成中：等待上游生成，或正在下载、处理、上传作品。
    COMPLETED = 1  # 已完成：作品已保存，启用 OSS 时已上传成功，可返回缓存地址。
    FAILED = 2  # 生成失败：已记录失败原因，后续查询直接返回失败信息。
    DELETED = 3  # 已删除：按任务不存在处理，不返回作品，也不查询上游。


# 上游状态与数据库状态分别维护，避免将查询异常当成生成失败。
# PENDING：排队中；RUNNING：执行中；SUSPENDED：已挂起，继续轮询。
PENDING_TASK_STATUSES = frozenset({"PENDING", "RUNNING", "SUSPENDED"})
# FAILED：生成失败；CANCELED：已取消；UNKNOWN：任务不存在或已过期。
FAILED_TASK_STATUSES = frozenset({"FAILED", "CANCELED", "UNKNOWN"})
