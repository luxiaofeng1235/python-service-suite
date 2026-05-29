"""
============================================
AI 对话日志 ORM 模型
============================================
主要功能：保存 AI 对话上下文，用于 chat_id 续聊和重生成。
"""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer

from app.database import Base


class AiChatLog(Base):
    """AI 对话日志表 ORM 模型"""

    __tablename__ = "ai_chat_log"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="id")
    user_id = Column(Integer, nullable=False, default=0, comment="用户ID")
    model_id = Column(Integer, nullable=False, default=0, comment="模型类型")
    chat = Column(JSON, nullable=False, default=list, comment="聊天消息JSON")
    create_time = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    update_time = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间"
    )

    def __repr__(self) -> str:
        return f"<AiChatLog(id={self.id}, user_id={self.user_id}, model_id={self.model_id})>"
