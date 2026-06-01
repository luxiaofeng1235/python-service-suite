"""
============================================
健康检查工具类
============================================
封装 MySQL、Redis 等依赖服务的连通性检查逻辑。
"""

from typing import Any

from sqlalchemy import text


class HealthChecker:
    """服务健康检查器"""

    @staticmethod
    async def check_mysql(engine) -> dict[str, Any]:
        """检查 MySQL 连通性"""
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @staticmethod
    async def check_redis(redis_client, redis_url: str | None) -> dict[str, Any]:
        """检查 Redis 连通性"""
        if not redis_url:
            return {"status": "unconfigured"}
        try:
            if redis_client.client is not None:
                await redis_client.client.ping()
            return {"status": "ok"}
        except RuntimeError:
            return {"status": "unconfigured"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
