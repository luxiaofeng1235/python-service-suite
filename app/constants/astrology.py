"""
============================================
Astrology Agent Constants - Message lifecycle
============================================
Defines persisted message statuses for complete and interrupted Agent responses.
"""

from enum import IntEnum


class ChatMessageStatus(IntEnum):
    """Persisted Agent message status."""

    GENERATING = 0  # 生成中
    COMPLETED = 1  # 已完成
    FAILED = 2  # 生成失败
    INTERRUPTED = 3  # 流式输出中断
