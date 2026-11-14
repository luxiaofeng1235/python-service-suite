"""
============================================
聊天消息常量 - Agent 消息生命周期
============================================
定义所有 Agent 共用的消息存储状态，与数据库状态值保持一致。
"""

from enum import IntEnum


class ChatMessageStatus(IntEnum):
    """对应 chat_messages.status 的消息状态。"""

    GENERATING = 0  # 生成中
    COMPLETED = 1  # 已完成
    FAILED = 2  # 生成失败
    INTERRUPTED = 3  # 流式输出中断
