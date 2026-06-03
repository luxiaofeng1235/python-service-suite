"""
============================================
时间工具类
============================================
常用时间操作方法，方便 CRUD 直接使用。

from app.utils.time_ import TimeUtil
"""

import calendar
from datetime import date, datetime, timedelta
from typing import Tuple

from dateutil.parser import isoparse


class TimeUtil:
    """时间工具类"""

    # ==================== 当前时间 ====================

    @staticmethod
    def unix() -> int:
        """当前秒级时间戳"""
        return int(datetime.now().timestamp())

    @staticmethod
    def datetime_str() -> str:
        """当前时间  YYYY-MM-DD HH:mm:ss"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def date_str() -> str:
        """当前日期  YYYY-MM-DD"""
        return datetime.now().strftime("%Y-%m-%d")

    # ==================== 时间戳 ↔ 字符串 ====================

    @staticmethod
    def unix_to_datetime(t: int) -> str:
        """Unix 秒 → YYYY-MM-DD HH:mm:ss"""
        return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def unix_to_date(t: int) -> str:
        """Unix 秒 → YYYY-MM-DD"""
        return datetime.fromtimestamp(t).strftime("%Y-%m-%d")

    @staticmethod
    def date_to_unix(s: str) -> int:
        """日期/时间字符串 → Unix 秒
        支持: YYYY-MM-DD / YYYY-MM-DD HH:mm:ss / ISO8601
        """
        if not s:
            return 0
        if "T" in s:
            try:
                return int(isoparse(s).timestamp())
            except ValueError:
                return 0
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y%m%d"):
            try:
                return int(datetime.strptime(s, fmt).timestamp())
            except ValueError:
                continue
        return 0

    # ==================== 今日/昨日/明日 ====================

    @staticmethod
    def today_start_unix() -> int:
        """今天 00:00:00 Unix"""
        d = date.today()
        return int(datetime(d.year, d.month, d.day).timestamp())

    @staticmethod
    def today_end_unix() -> int:
        """今天 23:59:59 Unix"""
        d = date.today()
        return int(datetime(d.year, d.month, d.day, 23, 59, 59).timestamp())

    @staticmethod
    def yesterday_start_unix() -> int:
        """昨天 00:00:00 Unix"""
        d = date.today() - timedelta(days=1)
        return int(datetime(d.year, d.month, d.day).timestamp())

    @staticmethod
    def tomorrow_date_str() -> str:
        """明天日期  YYYY-MM-DD"""
        return (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    # ==================== 相对时间计算（常用） ====================

    @staticmethod
    def ago_day_unix(days: int) -> int:
        """N 天前的 Unix 时间戳"""
        return int((datetime.now() - timedelta(days=days)).timestamp())

    @staticmethod
    def ago_day_range(days: int) -> Tuple[int, int]:
        """N 天前那天的 (00:00:00, 23:59:59)"""
        d = date.today() - timedelta(days=days)
        start = int(datetime(d.year, d.month, d.day).timestamp())
        end = int(datetime(d.year, d.month, d.day, 23, 59, 59).timestamp())
        return start, end

    @staticmethod
    def days_since(t: int) -> int:
        """距今多少自然日"""
        if t <= 0:
            return 0
        return (date.today() - datetime.fromtimestamp(t).date()).days

    # ==================== 月/周范围 ====================

    @staticmethod
    def month_range(month: int) -> Tuple[int, int]:
        """指定月份（1-12）的起止 Unix 时间戳"""
        if month < 1 or month > 12:
            return 0, 0
        year = date.today().year
        _, days = calendar.monthrange(year, month)
        start = int(datetime(year, month, 1).timestamp())
        end = int(datetime(year, month, days, 23, 59, 59).timestamp())
        return start, end

    @staticmethod
    def week_range() -> Tuple[int, int]:
        """本周一 00:00:00 ~ 本周日 23:59:59"""
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        start = int(datetime(monday.year, monday.month, monday.day).timestamp())
        end = int(datetime(sunday.year, sunday.month, sunday.day, 23, 59, 59).timestamp())
        return start, end

    # ==================== 人性化 ====================

    @staticmethod
    def format_before(t: int) -> str:
        """X分钟前 / X小时前 / X天前 ..."""
        diff = int(datetime.now().timestamp()) - t
        if diff < 60:
            return "刚刚"
        if diff < 3600:
            return f"{diff // 60}分钟前"
        if diff < 86400:
            return f"{diff // 3600}小时前"
        if diff < 2592000:
            return f"{diff // 86400}天前"
        if diff < 31536000:
            return f"{diff // 2592000}个月前"
        return f"{diff // 31536000}年前"
