"""
============================================
抽奖配置 ORM 模型
============================================
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, text
from sqlalchemy.dialects.mysql import TINYINT

from app.database import Base


class LotteryConfig(Base):
    """抽奖配置表"""
    __tablename__ = "lottery_configs"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    scene_key = Column(String(100), nullable=False, unique=True, comment="场景标识")
    name = Column(String(100), nullable=False, default="", comment="场景名称")
    config_json = Column(Text, nullable=False, comment="完整抽奖配置 JSON")
    status = Column(TINYINT(1), nullable=False, default=1, comment="1=启用 0=禁用")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    def __repr__(self):
        return f"<LotteryConfig(id={self.id}, scene_key='{self.scene_key}')>"
