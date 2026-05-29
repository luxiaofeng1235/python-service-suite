"""
============================================
验证码 ORM 模型 — SQLAlchemy 数据库表映射
============================================
用于存储邮件验证码（密码重置、邮箱验证等场景）
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.database import Base


class VerificationCode(Base):
    """验证码表 ORM 模型"""

    __tablename__ = "verification_codes"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="id")
    email = Column(String(255), nullable=False, index=True, comment="邮箱")
    code = Column(String(6), nullable=False, comment="6位验证码")
    purpose = Column(String(50), nullable=False, default="password_reset", comment="用途")
    expires_at = Column(DateTime, nullable=False, comment="过期时间")
    used = Column(Boolean, default=False, nullable=False, comment="是否已使用")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")

    def __repr__(self) -> str:
        return f"<VerificationCode(id={self.id}, email='{self.email}', used={self.used})>"
