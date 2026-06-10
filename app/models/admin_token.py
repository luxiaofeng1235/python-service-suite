"""
============================================
后台管理员 Token ORM 模型
============================================
管理员登录后的短 Token，独立于前台用户的 user_tokens。
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.database import Base


class AdminToken(Base):
    """管理员 Token 表 ORM 模型"""

    __tablename__ = "admin_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="id")
    admin_id = Column(Integer, nullable=False, index=True, comment="管理员ID")
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
        return f"<AdminToken(id={self.id}, admin_id={self.admin_id}, is_active={self.is_active})>"
