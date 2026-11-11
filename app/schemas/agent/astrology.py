"""
============================================
Astrology Schemas - Profile and horoscope tool inputs
============================================
Validates business data without accepting user identity from model-generated arguments.
"""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

ZodiacSign = Literal[
    "aries",
    "taurus",
    "gemini",
    "cancer",
    "leo",
    "virgo",
    "libra",
    "scorpio",
    "sagittarius",
    "capricorn",
    "aquarius",
    "pisces",
]
FortuneAspect = Literal["all", "love", "career", "wealth"]


class EmptyToolRequest(BaseModel):
    """Reject arguments for tools that use backend identity exclusively."""

    model_config = ConfigDict(extra="forbid")


class HoroscopeToolRequest(BaseModel):
    """Describe a public daily fortune lookup."""

    model_config = ConfigDict(extra="forbid")

    constellation: ZodiacSign | None = Field(
        None, description="Zodiac sign; omitted uses the user's profile"
    )
    fortune_date: date | None = Field(
        None, description="Fortune date; omitted uses today's business date"
    )
    aspect: FortuneAspect = Field("all", description="Fortune topic: all, love, career or wealth")


class GeneratedHoroscope(BaseModel):
    """Validate AI-authored entertainment content before caching it."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: str = Field(..., min_length=1, max_length=600, description="Daily overview")
    love: str = Field(..., min_length=1, max_length=400, description="Relationship advice")
    career: str = Field(..., min_length=1, max_length=400, description="Work and study advice")
    wealth: str = Field(..., min_length=1, max_length=400, description="Everyday spending advice")
    advice: str = Field(..., min_length=1, max_length=400, description="Actionable daily suggestion")


class AstrologyProfileUpdateRequest(BaseModel):
    """Update explicitly supplied birth-profile fields."""

    model_config = ConfigDict(extra="forbid")

    birthday: date | None = Field(None, description="Gregorian birth date")
    birth_time: time | None = Field(None, description="Local birth time; null when unknown")
    birth_timezone: str | None = Field(None, max_length=64, description="IANA birth timezone")
    birth_place: str | None = Field(None, max_length=255, description="Birthplace name")
    birth_latitude: Decimal | None = Field(
        None, ge=-90, le=90, decimal_places=7, description="Birthplace latitude"
    )
    birth_longitude: Decimal | None = Field(
        None, ge=-180, le=180, decimal_places=7, description="Birthplace longitude"
    )
    constellation: ZodiacSign | None = Field(None, description="Default zodiac sign")

    @field_validator("birthday")
    @classmethod
    def validate_birthday(cls, value: date | None) -> date | None:
        """Reject future birth dates."""
        if value is not None and value > date.today():
            raise ValueError("出生日期不能晚于今天")
        return value

    @field_validator("birth_timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        """Require an existing IANA timezone when supplied."""
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError("出生时区无效") from exc
        return value


class HoroscopeCacheRequest(BaseModel):
    """Accept a validated cache entry from a backend data source."""

    model_config = ConfigDict(extra="forbid")

    constellation: ZodiacSign = Field(..., description="Zodiac sign")
    fortune_date: date = Field(..., description="Fortune business date")
    aspect: FortuneAspect = Field("all", description="Fortune topic")
    score: int | None = Field(None, ge=0, le=100, description="Fortune score")
    raw_data: dict[str, JsonValue] = Field(..., description="Structured horoscope content")
    source: str | None = Field(
        None, max_length=100, description="Data provider or generation source"
    )
    expires_at: datetime | None = Field(None, description="Optional local cache expiry time")

    @field_validator("expires_at")
    @classmethod
    def validate_expiry(cls, value: datetime | None) -> datetime | None:
        """Match the project's local, timezone-naive DATETIME convention."""
        if value is not None and value.tzinfo is not None:
            raise ValueError("缓存过期时间请使用服务器本地时间，不携带时区偏移")
        return value
