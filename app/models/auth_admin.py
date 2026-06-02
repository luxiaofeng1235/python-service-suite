"""
============================================
后台管理员 ORM 模型
============================================
独立于 users 表，管理员账号单独管理。
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.database import Base


class AuthAdmin(Base):
    """后台管理员表 ORM 模型"""

    __tablename__ = "auth_admins"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="管理员ID")
    username = Column(String(50), unique=True, nullable=False, comment="用户名")
    password_hash = Column(String(255), nullable=False, comment="密码哈希")
    nickname = Column(String(50), nullable=False, default="", comment="昵称")
    is_super = Column(Boolean, default=False, nullable=False, comment="是否超管")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否启用")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="更新时间",
    )

    def __repr__(self) -> str:
        return f"<AuthAdmin(id={self.id}, username={self.username}, is_super={self.is_super})>"
