"""
============================================
AI Generation Task Model - SQLAlchemy mapping
============================================
Stores generation parameters, task ownership, and cached results from AiLogic.php.
"""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.dialects.mysql import TINYINT

from app.database import Base


class AiToWork(Base):
    """Persist asynchronous AI generation tasks."""

    __tablename__ = "ai_to_work"
    __table_args__ = (
        UniqueConstraint("task_id", name="task_id"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_general_ci",
            "comment": "ai作品表",
        },
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="id")
    user_id = Column(Integer, nullable=False, comment="用户id")
    task_id = Column(String(255), nullable=True, comment="任务id")
    params = Column(JSON, nullable=False, comment="生成参数")
    work = Column(JSON(none_as_null=True), nullable=True, comment="作品")
    type = Column(
        SmallInteger().with_variant(TINYINT(display_width=1), "mysql"),
        nullable=True, default=1, server_default=text("1"), comment="1图片，2视频",
    )
    status = Column(
        SmallInteger().with_variant(TINYINT(display_width=1), "mysql"),
        nullable=True, default=0, server_default=text("0"),
        comment="类型，0生成中，1已生成，2生成失败，3已删除",
    )
    create_time = Column(DateTime, nullable=True, default=datetime.now)
    update_time = Column(
        DateTime, nullable=True, default=datetime.now, onupdate=datetime.now
    )

    def __repr__(self) -> str:
        return f"<AiToWork(id={self.id}, task_id={self.task_id!r}, status={self.status})>"
