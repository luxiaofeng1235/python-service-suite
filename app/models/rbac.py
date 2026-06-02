"""
============================================
RBAC 数据模型 — 三表结构
============================================
permissions：权限目录（管理后台可勾选的条目）
roles：角色辅助表（供管理后台下拉展示用）
casbin_rule：Casbin 标准策略表（权限鉴定核心）
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.database import Base


class Permission(Base):
    """权限目录表 — 定义系统中所有可分配的权限"""

    __tablename__ = "auth_permissions"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="权限ID")
    resource = Column(String(50), nullable=False, comment="资源名（如 user / role / permission）")
    action = Column(String(50), nullable=False, comment="操作名（如 list / create / delete）")
    description = Column(String(255), nullable=True, comment='中文说明（如 "查看用户列表"）')
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")

    def __repr__(self) -> str:
        return f"<Permission(id={self.id}, {self.resource}:{self.action})>"


class CasbinRule(Base):
    """Casbin 策略规则表（兼容 Casbin 标准 schema）"""

    __tablename__ = "auth_casbin_rule"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    ptype = Column(String(10), nullable=False, index=True, comment="策略类型：p=权限, g=角色归属")
    v0 = Column(String(100), nullable=False, index=True, comment="sub（角色名 或 用户ID）")
    v1 = Column(String(100), nullable=False, comment="obj（资源 或 角色名）")
    v2 = Column(String(100), default="", comment="act（动作）")
    v3 = Column(String(100), default="", comment="预留")
    v4 = Column(String(100), default="", comment="预留")
    v5 = Column(String(100), default="", comment="预留")

    def __repr__(self) -> str:
        return (
            f"<CasbinRule(ptype='{self.ptype}', "
            f"v0='{self.v0}', v1='{self.v1}', v2='{self.v2}')>"
        )


class Role(Base):
    """角色定义表（辅助展示，不参与鉴权逻辑）"""

    __tablename__ = "auth_roles"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="角色ID")
    name = Column(String(50), unique=True, nullable=False, comment="角色名（与 casbin_rule.v0 对应）")
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
