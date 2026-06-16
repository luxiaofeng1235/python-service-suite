"""
============================================
文章主表 ORM 模型 — SQLAlchemy 数据库表映射
============================================
存储文章的核心字段，包含标题、内容、状态等。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, JSON, SmallInteger, String, Text

from app.database import Base


class CmsArticle(Base):
    """文章主表 ORM 模型"""

    __tablename__ = "cms_articles"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="文章ID")
    title = Column(String(255), nullable=False, comment="文章标题")
    slug = Column(String(255), unique=True, nullable=False, comment="URL别名")
    category_id = Column(Integer, nullable=False, index=True, comment="所属分类ID")
    author = Column(String(100), nullable=True, comment="作者/编辑")
    summary = Column(String(500), nullable=True, comment="文章摘要/简介")
    content = Column(Text, nullable=False, comment="文章正文内容(支持HTML或Markdown)")
    cover_image = Column(String(255), nullable=True, comment="封面图URL")
    status = Column(SmallInteger, nullable=False, default=0, comment="状态: 0-草稿, 1-已发布, 2-下架")
    view_count = Column(Integer, nullable=False, default=0, comment="浏览次数")
    tag_ids = Column(JSON, nullable=True, comment="关联标签ID列表")
    published_at = Column(DateTime, nullable=True, comment="实际发布时间")
    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at = Column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
        comment="更新时间",
    )

    def __repr__(self) -> str:
        return f"<CmsArticle(id={self.id}, title='{self.title}', status={self.status})>"
