"""
============================================
抽奖记录 ORM 模型
============================================
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint, text

from app.database import Base


class LotteryRecord(Base):
    """用户抽奖记录表"""

    __tablename__ = "lottery_records"
    __table_args__ = (
        UniqueConstraint("user_id", "scene_key", "request_id", "draw_index", name="uk_lottery_record_request_index"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    user_id = Column(Integer, nullable=False, comment="用户ID")
    scene_key = Column(String(100), nullable=False, comment="抽奖场景标识")
    request_id = Column(String(64), nullable=True, comment="客户端幂等请求ID")
    draw_index = Column(Integer, nullable=False, default=0, comment="同一请求内抽奖序号")
    prize_type = Column(String(50), nullable=False, default="", comment="奖励类型")
    prize_id = Column(String(100), nullable=True, comment="具体奖品ID")
    amount = Column(String(50), nullable=False, default="0", comment="奖励金额/数量")
    props_json = Column(Text, nullable=True, comment="附加奖品信息JSON")
    result_json = Column(Text, nullable=False, comment="完整抽奖结果JSON")
    grant_status = Column(String(20), nullable=False, default="pending", comment="发奖状态 pending/success/failed")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间")
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment="更新时间",
    )

    def __repr__(self):
        return f"<LotteryRecord(id={self.id}, user_id={self.user_id}, scene_key='{self.scene_key}')>"
