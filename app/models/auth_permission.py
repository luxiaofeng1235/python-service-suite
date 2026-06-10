"""
============================================
权限目录模型 — auth_permissions 表
============================================
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from app.database import Base


class Permission(Base):
    """权限目录表 — 定义系统中所有可分配的权限"""

    __tablename__ = "auth_permissions"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="权限ID")
    resource = Column(String(50), nullable=False, comment="资源名（如 user / role / permission）")
    action = Column(String(50), nullable=False, comment="操作名（如 list / create / delete）")
    description = Column(String(255), nullable=True, comment='中文说明（如 "查看用户列表"）')
    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="创建时间")

    def __repr__(self) -> str:
        return f"<Permission(id={self.id}, {self.resource}:{self.action})>"
