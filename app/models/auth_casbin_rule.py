"""
============================================
Casbin 策略规则模型 — auth_casbin_rule 表
============================================

Casbin 规则表遵循标准 Casbin 策略格式：
  p, sub, obj, act          → 权限规则（用户/角色可对某资源做某操作）
  g, user, role             → 角色归属（用户属于哪个角色）

字段映射说明（v0～v5 为 Casbin 固定命名）：
  ptype — 策略类型（p=权限策略, g=角色继承）
  v0    — sub：主体（p 时为角色名, g 时为用户ID）
  v1    — obj：客体（p 时为资源名, g 时为角色名）
  v2    — act：操作（仅 p 时使用，如 list/create/delete）
  v3~v5 — Casbin 标准预留字段，本系统未使用
"""

from sqlalchemy import Column, Integer, String, UniqueConstraint

from app.database import Base


class CasbinRule(Base):
    """Casbin 策略规则表（兼容 Casbin 标准 schema）"""

    __tablename__ = "auth_casbin_rule"
    __table_args__ = (
        # 整行唯一，让分配权限/绑定角色的幂等由 DB 兜底，杜绝并发写入重复策略
        UniqueConstraint("ptype", "v0", "v1", "v2", "v3", "v4", "v5", name="uk_casbin_rule"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    ptype = Column(String(10), nullable=False, index=True, comment="策略类型：p=权限, g=角色归属")
    v0 = Column(String(100), nullable=False, index=True, comment="sub：主体（角色名 或 用户ID）")
    v1 = Column(String(100), nullable=False, comment="obj：客体（资源名 如 user/role，或 g 时的角色名）")
    v2 = Column(String(100), default="", comment="act：操作（如 list/create/delete）")
    v3 = Column(String(100), default="", comment="预留字段（Casbin 标准保留未使用）")
    v4 = Column(String(100), default="", comment="预留字段（Casbin 标准保留未使用）")
    v5 = Column(String(100), default="", comment="预留字段（Casbin 标准保留未使用）")

    def __repr__(self) -> str:
        return (
            f"<CasbinRule(ptype='{self.ptype}', "
            f"v0='{self.v0}', v1='{self.v1}', v2='{self.v2}')>"
        )
