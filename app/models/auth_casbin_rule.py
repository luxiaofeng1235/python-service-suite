"""
============================================
Casbin 策略规则模型 — auth_casbin_rule 表
============================================
"""

from sqlalchemy import Column, Integer, String

from app.database import Base


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
