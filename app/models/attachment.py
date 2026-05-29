"""
============================================
附件/文件上传 ORM 模型 — SQLAlchemy 数据库表映射
============================================
主要功能：记录用户上传的图片、视频等文件的元数据信息。
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from app.database import Base


class Attachment(Base):
    """附件/文件上传记录表"""

    __tablename__ = "attachment"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="文件ID")
    user_id = Column(Integer, nullable=False, index=True, comment="上传用户ID")
    original_name = Column(String(255), nullable=False, comment="原始文件名")
    stored_name = Column(String(255), nullable=False, comment="存储文件名")
    file_path = Column(String(500), nullable=False, comment="文件相对路径")
    file_size = Column(Integer, nullable=False, comment="文件大小（字节）")
    mime_type = Column(String(100), nullable=False, comment="MIME 类型")
    file_type = Column(String(20), nullable=False, comment="文件分类：image / video / other")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="上传时间")

    def __repr__(self) -> str:
        return f"<Attachment(id={self.id}, original='{self.original_name}', type='{self.file_type}')>"
