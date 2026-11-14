"""
============================================
聊天消息模型 - SQLAlchemy 数据库表映射
============================================
保存 Agent 对话消息、工具调用记录及流式消息的执行状态。
"""

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

from app.constants.chat import ChatMessageStatus
from app.database import Base
from app.utils.time_ import TimeUtil


class ChatMessage(Base):
    """映射所有 Agent 共用的聊天消息及工具调用记录。"""

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
            "comment": "智能体聊天消息及工具调用记录表",
        },
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="消息ID")
    session_id = Column(String(36), nullable=False, comment="关联聊天会话ID，对应chat_sessions.id")
    role = Column(String(20), nullable=False, comment="消息角色：system系统、user用户、assistant助手、tool工具")
    content = Column(
        Text, nullable=True, comment="消息文本内容或序列化JSON，纯工具调用时可以为空"
    )
    tool_name = Column(String(64), nullable=True, comment="工具函数名称")
    tool_calls = Column(
        JSON(none_as_null=True),
        nullable=True,
        comment="助手发起的工具调用信息，包含调用ID、函数名称及参数",
    )
    tool_call_id = Column(String(128), nullable=True, comment="工具调用关联ID，用于匹配工具执行结果")
    status = Column(
        SmallInteger,
        nullable=False,
        default=ChatMessageStatus.COMPLETED,
        server_default=text("1"),
        comment="消息状态：0生成中、1已完成、2执行失败、3已中断",
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
        return f"<ChatMessage(id={self.id}, session_id={self.session_id!r}, role={self.role!r})>"
