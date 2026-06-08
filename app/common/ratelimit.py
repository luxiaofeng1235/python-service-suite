"""
============================================
速率限制工具模块（支持内存 / Redis 双后端）
============================================
基于 IP + Key 的滑动窗口限速，用于短时间窗口内防止暴力枚举。
默认使用内存后端（进程内），可选 Redis 后端实现跨进程限速。

使用方式：
    from app.common.ratelimit import RateLimiter

    # 内存后端（默认）
    limiter = RateLimiter(max_requests=3, window_seconds=300)
    if not await limiter.check("forgot:user@example.com"):
        raise AppException(msg="请求过于频繁，请稍后再试")

    # Redis 后端（需配置 REDIS_URL）
    limiter = RateLimiter(max_requests=3, window_seconds=300, use_redis=True)
    if not await limiter.check("forgot:user@example.com"):
        raise AppException(msg="请求过于频繁，请稍后再试")
"""

import time
from collections import defaultdict
from threading import Lock

try:
    from app.pkg.redis_client import redis_client
except ImportError:
    redis_client = None


class RateLimiter:
    """速率限制器 — 支持内存后端（默认）与 Redis 后端"""

    def __init__(
        self,
        max_requests: int = 10,
        window_seconds: int = 300,
        use_redis: bool = False,
    ):
        """
        Args:
            max_requests: 时间窗口内允许的最大请求数
            window_seconds: 时间窗口长度（秒）
            use_redis: True 使用 Redis 后端（需配置 REDIS_URL），False 使用内存后端
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.use_redis = use_redis
        self._records: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    # ── Redis 辅助方法 ──────────────────────────────────────

    def _redis_key(self, key: str) -> str:
        """生成 Redis 中使用的限速 key"""
        return f"ratelimit:{key}"

    async def _redis_check(self, key: str) -> bool:
        """基于 Redis 有序集合的滑动窗口检查"""
        now = time.time()
        cutoff = now - self.window_seconds
        redis_key = self._redis_key(key)
        c = redis_client.client

        pipe = c.pipeline()
        # 移除窗口外的记录
        pipe.zremrangebyscore(redis_key, 0, cutoff)
        # 查询当前窗口内的记录数
        pipe.zcard(redis_key)
        # 设置 TTL 以防止 key 永久残留
        pipe.expire(redis_key, self.window_seconds)
        _, count, _ = await pipe.execute()

        if count >= self.max_requests:
            return False

        # 记录本次请求时间戳
        await c.zadd(redis_key, {str(now): now})
        await c.expire(redis_key, self.window_seconds)
        return True

    async def _redis_remaining(self, key: str) -> int:
        """基于 Redis 查询剩余次数"""
        now = time.time()
        cutoff = now - self.window_seconds
        redis_key = self._redis_key(key)
        c = redis_client.client

        pipe = c.pipeline()
        pipe.zremrangebyscore(redis_key, 0, cutoff)
        pipe.zcard(redis_key)
        pipe.expire(redis_key, self.window_seconds)
        _, count, _ = await pipe.execute()

        return max(0, self.max_requests - count)

    # ── 内存后端（同步） ────────────────────────────────────

    def _mem_check(self, key: str) -> bool:
        """基于进程内内存的滑动窗口检查"""
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            records = self._records[key]
            self._records[key] = [t for t in records if t > cutoff]
            if len(self._records[key]) >= self.max_requests:
                return False
            self._records[key].append(now)
        return True

    def _mem_remaining(self, key: str) -> int:
        """基于进程内内存查询剩余次数"""
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            records = [t for t in self._records[key] if t > cutoff]
            self._records[key] = records
            return max(0, self.max_requests - len(records))

    # ── 公开方法（async，统一接口） ─────────────────────────

    async def check(self, key: str) -> bool:
        """
        检查指定 key 是否超过速率限制。

        Args:
            key: 限速标识，建议格式 "{action}:{identifier}"

        Returns:
            True: 允许请求
            False: 超过限制，应拒绝请求
        """
        if self.use_redis:
            return await self._redis_check(key)
        return self._mem_check(key)

    async def remaining(self, key: str) -> int:
        """返回 key 在当前窗口内还剩多少次请求机会"""
        if self.use_redis:
            return await self._redis_remaining(key)
        return self._mem_remaining(key)
