"""
============================================
用户登录 Token ORM 模型
============================================
主要功能：保存用户登录后的短 Token、过期时间和有效状态。
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.database import Base


class UserToken(Base):
    """用户登录 Token 表 ORM 模型"""

    __tablename__ = "user_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="id")
    user_id = Column(Integer, nullable=False, index=True, comment="用户ID")
    token = Column(String(64), unique=True, nullable=False, index=True, comment="登录Token")
    expires_at = Column(DateTime, nullable=False, comment="过期时间")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否有效")
    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at = Column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
        comment="更新时间",
    )

    def __repr__(self) -> str:
        return f"<UserToken(id={self.id}, user_id={self.user_id}, is_active={self.is_active})>"
