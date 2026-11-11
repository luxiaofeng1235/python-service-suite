"""
============================================
Chat Session Model - SQLAlchemy mapping
============================================
Stores Agent conversation ownership and titles independently of legacy AI chat logs.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Index, Integer, String, text

from app.database import Base


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
            "comment": "Agent chat sessions",
        },
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()), comment="Session UUID")
    user_id = Column(Integer, nullable=False, comment="Existing users.id")
    agent = Column(
        String(50),
        nullable=False,
        default="astrology",
        server_default="astrology",
        comment="Agent identifier, e.g. astrology or divination",
    )
    active_run_id = Column(String(36), nullable=True, comment="Current execution lease UUID")
    run_expires_at = Column(DateTime, nullable=True, comment="Execution lease expiry time")
    title = Column(
        String(100),
        nullable=False,
        default="新对话",
        server_default="新对话",
        comment="Conversation title",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="Created time",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment="Updated time",
    )

    def __repr__(self) -> str:
        return f"<ChatSession(id={self.id!r}, user_id={self.user_id})>"
