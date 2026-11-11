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
            "comment": "Shared daily horoscope cache",
        },
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Cache ID")
    constellation = Column(String(20), nullable=False, comment="Zodiac sign, e.g. aries or pisces")
    fortune_date = Column(
        Date, nullable=False, comment="Fortune date in the configured business timezone"
    )
    aspect = Column(
        String(30),
        nullable=False,
        default="all",
        server_default="all",
        comment="Fortune aspect: all, love, career, wealth",
    )
    score = Column(Integer, nullable=True, comment="Fortune score from 0 to 100")
    raw_data = Column(JSON, nullable=False, comment="Structured horoscope content")
    source = Column(String(100), nullable=True, comment="Data provider or generation source")
    expires_at = Column(DateTime, nullable=True, comment="Optional cache expiry time")
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="Created time",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment="Updated time",
    )

    def __repr__(self) -> str:
        return (
            f"<HoroscopeCache(id={self.id}, constellation={self.constellation!r}, "
            f"fortune_date={self.fortune_date}, aspect={self.aspect!r})>"
        )
