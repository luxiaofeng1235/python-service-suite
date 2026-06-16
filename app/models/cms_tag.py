"""
============================================
文章标签 ORM 模型 — SQLAlchemy 数据库表映射
============================================
存储文章标签，用于文章分类和检索。
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from app.database import Base


class CmsTag(Base):
    """文章标签 ORM 模型"""

    __tablename__ = "cms_tags"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="标签ID")
    name = Column(String(50), unique=True, nullable=False, comment="标签名称")
    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="创建时间")

    def __repr__(self) -> str:
        return f"<CmsTag(id={self.id}, name='{self.name}')>"
