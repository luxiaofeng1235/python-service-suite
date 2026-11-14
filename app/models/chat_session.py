"""
============================================
Chat Session Model - SQLAlchemy mapping
============================================
Stores Agent conversation ownership and titles independently of legacy AI chat logs.
"""

from uuid import uuid4

from sqlalchemy import Column, DateTime, Index, Integer, String, text

from app.database import Base
from app.utils.time_ import TimeUtil


class ChatSession(Base):
    """Group Agent messages into a user-owned conversation."""

    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index("idx_chat_sessions_user_updated", "user_id", "updated_at"),
        Index("idx_chat_sessions_user_agent_updated", "user_id", "agent", "updated_at"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "智能体聊天会话表",
        },
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()), comment="会话UUID")
    user_id = Column(Integer, nullable=False, comment="用户ID，关联users.id")
    agent = Column(
        String(50),
        nullable=False,
        default="astrology",
        server_default="astrology",
        comment="Agent智能体标识，例如astrology星座、divination占卜",
    )
    active_run_id = Column(String(36), nullable=True, comment="当前执行任务租约UUID")
    run_expires_at = Column(DateTime, nullable=True, comment="当前执行任务租约过期时间")
    title = Column(
        String(100),
        nullable=False,
        default="新对话",
        server_default="新对话",
        comment="对话标题",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=TimeUtil.get_date,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="创建时间",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=TimeUtil.get_date,
        onupdate=TimeUtil.get_date,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment="更新时间",
    )

    def __repr__(self) -> str:
        return f"<ChatSession(id={self.id!r}, user_id={self.user_id})>"
