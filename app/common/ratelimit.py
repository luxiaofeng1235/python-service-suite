"""
============================================
内存级速率限制工具模块
============================================
基于 IP + Key 的滑动窗口限速，用于短时间窗口内防止暴力枚举。

使用方式：
    from app.common.ratelimit import RateLimiter

    limiter = RateLimiter(max_requests=3, window_seconds=300)
    if not await limiter.check("forgot:user@example.com"):
        raise AppException(msg="请求过于频繁，请稍后再试")
"""

import time
from collections import defaultdict
from threading import Lock


class RateLimiter:
    """内存级速率限制器 — 无需 Redis，进程内滑动窗口"""

    def __init__(self, max_requests: int = 10, window_seconds: int = 300):
        """
        Args:
            max_requests: 时间窗口内允许的最大请求数
            window_seconds: 时间窗口长度（秒）
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._records: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def check(self, key: str) -> bool:
        """
        检查指定 key 是否超过速率限制。

        Args:
            key: 限速标识，建议格式 "{action}:{identifier}"，如 "forgot:user@example.com"

        Returns:
            True: 允许请求
            False: 超过限制，应拒绝请求
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            records = self._records[key]
            # 清理过期记录
            self._records[key] = [t for t in records if t > cutoff]

            # 判断是否超限
            if len(self._records[key]) >= self.max_requests:
                return False

            # 记录本次请求
            self._records[key].append(now)

        return True

    def remaining(self, key: str) -> int:
        """返回 key 在当前窗口内还剩多少次请求机会"""
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            records = [t for t in self._records[key] if t > cutoff]
            self._records[key] = records
            return max(0, self.max_requests - len(records))
