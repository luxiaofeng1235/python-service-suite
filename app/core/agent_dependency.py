"""
============================================
智能体依赖注入 - 获取应用共享的商品服务
============================================
从应用生命周期获取商品服务，避免每次请求创建新的本地向量客户端和线程。
"""

from fastapi import Request

from app.common.exception import AppException
from app.core.config import settings
from app.services.agent.goods_service import GoodsService


def get_goods_service(request: Request) -> GoodsService:
    """向控制器提供共享服务，功能关闭或启动未完成时返回业务错误。"""
    if not settings.GOODS_AGENT_ENABLED:
        raise AppException(msg="商品 Agent 未启用")
    service = getattr(request.app.state, "goods_service", None)
    if service is None:
        raise AppException(msg="商品 Agent 尚未初始化，请稍后重试")
    return service
