"""
============================================
Horoscope Cache Model - SQLAlchemy mapping
============================================
Caches shared daily fortunes by zodiac sign, business date, and topic.
Personal birth-chart interpretations are not stored in this shared cache.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    text,
)

from app.database import Base


class HoroscopeCache(Base):
    """Store one shared fortune per sign, date and aspect."""

    __tablename__ = "horoscope_cache"
    __table_args__ = (
        UniqueConstraint(
            "constellation", "fortune_date", "aspect", name="uk_constellation_date_aspect"
        ),
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_horoscope_cache_score"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "星座每日运势共享缓存表",
        },
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="缓存ID")
    constellation = Column(String(20), nullable=False, comment="星座标识，例如aries白羊座、pisces双鱼座")
    fortune_date = Column(
        Date, nullable=False, comment="运势日期（按照配置的业务时区）"
    )
    aspect = Column(
        String(30),
        nullable=False,
        default="all",
        server_default="all",
        comment="运势维度：all全部、love爱情、career事业、wealth财运",
    )
    score = Column(Integer, nullable=True, comment="运势评分（0-100分）")
    raw_data = Column(JSON, nullable=False, comment="结构化星座运势内容")
    source = Column(String(100), nullable=True, comment="数据来源（第三方数据服务商或AI生成来源）")
    expires_at = Column(DateTime, nullable=True, comment="缓存过期时间（可选）")
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="创建时间",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment="更新时间",
    )

    def __repr__(self) -> str:
        return (
            f"<HoroscopeCache(id={self.id}, constellation={self.constellation!r}, "
            f"fortune_date={self.fortune_date}, aspect={self.aspect!r})>"
        )
