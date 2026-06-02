"""
============================================
工具接口控制器层
============================================
提供健康检查等运维工具接口。
"""

from fastapi import APIRouter

from app.common.health_check import HealthChecker
from app.common.response import Response
from app.core.config import settings
from app.core.redis_client import redis_client
from app.database import engine

# ==================== 路由定义 ====================
router = APIRouter(prefix="/api", tags=["工具接口"])


# ==================== 健康检查 ====================


@router.get("/health", summary="健康检查")
async def health_check():
    """
    服务健康检查接口（无鉴权，白名单）

    返回服务运行状态，用于监控和负载均衡健康探测。
    同时检查 MySQL 和 Redis 的连通性。
    """
    checks = {
        "mysql": await HealthChecker.check_mysql(engine),
        "redis": await HealthChecker.check_redis(redis_client, settings.REDIS_URL),
    }

    mysql_healthy = checks["mysql"]["status"] == "ok"
    redis_healthy = checks["redis"]["status"] in ("ok", "unconfigured")
    all_healthy = mysql_healthy and redis_healthy

    return Response.success(
        data={
            "status": "running" if all_healthy else "degraded",
            "version": "1.0.0",
            "service": "FastAPI AI Service",
            **checks,
        },
        msg="服务运行正常" if all_healthy else "部分服务异常",
    )
