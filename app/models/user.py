"""
============================================
用户 ORM 模型 — SQLAlchemy 数据库表映射
============================================
主要功能：定义前台用户账户模型，包含登录信息和状态标记。
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.database import Base


class User(Base):
    """用户表 ORM 模型"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="用户ID")
    username = Column(String(50), unique=True, nullable=False, comment="用户名")
    password_hash = Column(String(255), nullable=False, comment="密码哈希")
    nickname = Column(String(50), nullable=True, comment="昵称")
    email = Column(String(255), nullable=True, comment="邮箱")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否启用")
    is_deleted = Column(Boolean, default=False, nullable=False, comment="是否已注销（软删除）")
    deleted_at = Column(DateTime, nullable=True, comment="注销时间")
    last_login_ip = Column(String(45), nullable=True, comment="最后登录 IP")
    last_login_at = Column(DateTime, nullable=True, comment="最后登录时间")
    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at = Column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
        comment="更新时间",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}')>"
