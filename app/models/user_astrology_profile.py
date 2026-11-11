"""
============================================
User Astrology Profile Model - SQLAlchemy mapping
============================================
Stores one optional birth profile per existing frontend user.
Unknown birth times and locations remain null.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, Column, Date, DateTime, Integer, Numeric, String, Time, text

from app.database import Base


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
            "comment": "User astrology profiles",
        },
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Profile ID")
    user_id = Column(
        Integer,
        nullable=False,
        unique=True,
        index=True,
        comment="Existing users.id; one profile per user",
    )
    birthday = Column(Date, nullable=True, comment="Birth date in the Gregorian calendar")
    birth_time = Column(Time, nullable=True, comment="Local birth time; null when unknown")
    birth_timezone = Column(
        String(64), nullable=True, comment="IANA birth timezone, e.g. Asia/Shanghai"
    )
    birth_place = Column(String(255), nullable=True, comment="Birthplace name")
    birth_latitude = Column(Numeric(10, 7), nullable=True, comment="Birthplace latitude in degrees")
    birth_longitude = Column(
        Numeric(10, 7), nullable=True, comment="Birthplace longitude in degrees"
    )
    constellation = Column(
        String(20), nullable=True, comment="Default zodiac sign, e.g. aries or pisces"
    )
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
        return f"<UserAstrologyProfile(id={self.id}, user_id={self.user_id})>"
