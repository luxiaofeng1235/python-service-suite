"""
============================================
User Astrology Profile Model - SQLAlchemy mapping
============================================
Stores one optional birth profile per existing frontend user.
Unknown birth times and locations remain null.
"""

from sqlalchemy import CheckConstraint, Column, Date, DateTime, Integer, Numeric, String, Time, text

from app.database import Base
from app.utils.time_ import TimeUtil


class UserAstrologyProfile(Base):
    """Store birth information without duplicating the user account."""

    __tablename__ = "user_astrology_profiles"
    __table_args__ = (
        CheckConstraint("birth_latitude BETWEEN -90 AND 90", name="ck_astrology_birth_latitude"),
        CheckConstraint(
            "birth_longitude BETWEEN -180 AND 180", name="ck_astrology_birth_longitude"
        ),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "用户星座档案表",
        },
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="档案ID")
    user_id = Column(
        Integer,
        nullable=False,
        unique=True,
        index=True,
        comment="用户ID，",
    )
    birthday = Column(Date, nullable=True, comment="出生日期（公历）")
    birth_time = Column(Time, nullable=True, comment="出生时间（当地时间，未知时为空）")
    birth_timezone = Column(
        String(64), nullable=True, comment="出生地时区（IANA标准，例如Asia/Shanghai）"
    )
    birth_place = Column(String(255), nullable=True, comment="出生地点")
    birth_latitude = Column(Numeric(10, 7), nullable=True, comment="出生地纬度（度）")
    birth_longitude = Column(
        Numeric(10, 7), nullable=True, comment="出生地经度（度）"
    )
    constellation = Column(
        String(20), nullable=True, comment="默认星座（例如aries白羊座、pisces双鱼座）"
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=TimeUtil.get_date,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="创建时间",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=TimeUtil.get_date,
        onupdate=TimeUtil.get_date,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        comment="更新时间",
    )

    def __repr__(self) -> str:
        return f"<UserAstrologyProfile(id={self.id}, user_id={self.user_id})>"
