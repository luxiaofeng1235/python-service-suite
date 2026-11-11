"""
============================================
Chat Message Model - SQLAlchemy mapping
============================================
Stores ordered Agent messages, tool-call history, and streaming completion status.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    SmallInteger,
    String,
    Text,
    text,
)

from app.constants.astrology import ChatMessageStatus
from app.database import Base


class ChatMessage(Base):
    """Preserve text and tool messages for replaying an Agent conversation."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("idx_chat_messages_session_id", "session_id", "id"),
        CheckConstraint(
            "role IN ('system', 'user', 'assistant', 'tool')", name="ck_chat_messages_role"
        ),
        CheckConstraint("status IN (0, 1, 2, 3)", name="ck_chat_messages_status"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "Agent chat messages and tool calls",
        },
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Message ID")
    session_id = Column(String(36), nullable=False, comment="Related chat_sessions.id")
    role = Column(String(20), nullable=False, comment="Message role: system, user, assistant, tool")
    content = Column(
        Text, nullable=True, comment="Message text or serialized JSON; null for tool-only calls"
    )
    tool_name = Column(String(64), nullable=True, comment="Tool function name")
    tool_calls = Column(
        JSON(none_as_null=True),
        nullable=True,
        comment="Assistant tool calls with IDs, function names and arguments",
    )
    tool_call_id = Column(String(128), nullable=True, comment="Tool result correlation ID")
    status = Column(
        SmallInteger,
        nullable=False,
        default=ChatMessageStatus.COMPLETED,
        server_default=text("1"),
        comment="0=generating 1=completed 2=failed 3=interrupted",
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
        return f"<ChatMessage(id={self.id}, session_id={self.session_id!r}, role={self.role!r})>"
