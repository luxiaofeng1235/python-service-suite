"""
============================================
角色定义模型 — auth_roles 表
============================================
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.database import Base


class Role(Base):
    """角色定义表（name 即 casbin_rule 的关联键，承载角色的元信息与展示）"""

    __tablename__ = "auth_roles"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="角色ID")
    name = Column(String(50), unique=True, nullable=False, comment="角色名（与 casbin_rule.sub 对应）")
    description = Column(String(255), nullable=True, comment="角色描述")
    is_system = Column(Boolean, default=False, nullable=False, comment="系统内置角色（不可删除）")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="更新时间",
    )

    def __repr__(self) -> str:
        return f"<Role(id={self.id}, name='{self.name}')>"
