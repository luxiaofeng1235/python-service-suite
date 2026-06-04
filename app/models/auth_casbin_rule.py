"""
============================================
Casbin 策略规则模型 — auth_casbin_rule 表
============================================

Casbin 规则表遵循标准 Casbin 策略格式：
  p, sub, obj, act          → 权限规则（用户/角色可对某资源做某操作）
  g, user, role             → 角色归属（用户属于哪个角色）

字段映射说明（sub/obj/act）：
  ptype — 策略类型（p=权限策略, g=角色继承）
  sub   — 主体（p 时为角色名, g 时为用户ID）
  obj   — 客体（p 时为资源名, g 时为角色名）
  act   — 操作（仅 p 时使用，如 list/create/delete）
"""

from sqlalchemy import Column, Integer, String, UniqueConstraint

from app.database import Base


class CasbinRule(Base):
    """Casbin 策略规则表（兼容 Casbin 标准 schema）"""

    __tablename__ = "auth_casbin_rule"
    __table_args__ = (
        # 整行唯一，让分配权限/绑定角色的幂等由 DB 兜底，杜绝并发写入重复策略
        UniqueConstraint("ptype", "sub", "obj", "act", name="uk_casbin_rule"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    ptype = Column(String(10), nullable=False, index=True, comment="策略类型：p=权限, g=角色归属")
    sub = Column(String(100), nullable=False, index=True, comment="sub：主体（角色名 或 用户ID）")
    obj = Column(String(100), nullable=False, comment="obj：客体（资源名 如 user/role，或 g 时的角色名）")
    act = Column(String(100), default="", comment="act：操作（如 list/create/delete）")

    def __repr__(self) -> str:
        return (
            f"<CasbinRule(ptype='{self.ptype}', "
            f"sub='{self.sub}', obj='{self.obj}', act='{self.act}')>"
        )
