"""
============================================
Redis 客户端底座 — 统一封装，即插即用
============================================
使用方式：

    # 1. 在 .env 中配置 REDIS_URL
    # 2. 应用启动时自动连接（已在 main.py 中注册）
    # 3. 任意地方导入使用：

    from app.core.redis_client import redis_client

    await redis_client.set("key", "value", ex=3600)
    value = await redis_client.get("key")
    await redis_client.delete("key")
"""

from typing import Any

from redis.asyncio import Redis as AsyncRedis
from redis.asyncio.connection import ConnectionPool

from app.core.config import settings


class RedisClient:
    """Redis 异步客户端封装（单例模式）

    常用方法均委托给底层 redis.asyncio.Redis 实例，
    可直接调用 Redis 原生方法：

        await redis_client.client.hset(...)
        await redis_client.client.smembers(...)
    """

    def __init__(self) -> None:
        self._client: AsyncRedis | None = None

    @property
    def client(self) -> AsyncRedis:
        """获取底层 Redis 实例（检查就绪）"""
        if self._client is None:
            raise RuntimeError(
                "Redis 未初始化，请检查 REDIS_URL 是否正确配置，"
                "并确认应用启动时调用了 init_redis()"
            )
        return self._client

    # ==================== 生命周期 ====================

    async def init(self, url: str | None = None) -> None:
        """初始化 Redis 连接池（应用启动时调用）"""
        if self._client is not None:
            return  # 已初始化，幂等
        url = url or settings.REDIS_URL
        if not url:
            raise ValueError(
                "REDIS_URL 未配置，请在 .env 中设置 REDIS_URL 或调用 init_redis(url=...)"
            )
        pool = ConnectionPool.from_url(url, decode_responses=True)
        self._client = AsyncRedis(connection_pool=pool)
        # 验证连接是否可用
        await self._client.ping()

    async def close(self) -> None:
        """关闭 Redis 连接池（应用关闭时调用）"""
        if self._client is not None:
            pool = self._client.connection_pool
            await self._client.aclose()
            await pool.disconnect()
            self._client = None

    # ==================== 常用方法（快捷委托） ====================

    async def get(self, key: str) -> str | None:
        """获取字符串值"""
        return await self.client.get(key)

    async def set(self, key: str, value: Any, ex: int | None = None) -> bool:
        """设置字符串值，可选过期时间（秒）"""
        return await self.client.set(key, value, ex=ex)

    async def delete(self, *keys: str) -> int:
        """删除一个或多个键"""
        return await self.client.delete(*keys)

    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        return await self.client.exists(key) > 0

    async def expire(self, key: str, ex: int) -> bool:
        """设置过期时间（秒）"""
        return await self.client.expire(key, ex)

    async def ttl(self, key: str) -> int:
        """查看剩余过期时间（秒，-1 无过期，-2 不存在）"""
        return await self.client.ttl(key)


# ==================== 全局单例 ====================

redis_client = RedisClient()
"""全局 Redis 客户端实例，其他地方统一从此导入"""
