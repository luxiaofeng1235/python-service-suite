"""
============================================
中间件注册
============================================
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.middleware.request_log import RequestLogMiddleware
from app.middleware.encrypt import ApiEncryptMiddleware
from app.middleware.normalize import NotFoundMiddleware
from app.core.config import settings


def register_middleware(app: FastAPI) -> None:
    """注册中间件（先注册的最内层，最后注册的最外层，请求从外到内流经）"""
    # 执行顺序（请求进来方向）：加密中间件 → 日志中间件 → CORS → 路由

    # CORS（最先注册 = 最内层，放最后处理）
    origins = settings.CORS_ORIGINS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 请求日志
    app.add_middleware(RequestLogMiddleware)

    # 请求加解密（最后注册 = 最外层，最先处理请求，解密后 body 往下传）
    if settings.API_ENCRYPT_ENABLED:
        app.add_middleware(ApiEncryptMiddleware)

    # 404 统一响应（最外层，最早捕获响应中的 404）
    app.add_middleware(NotFoundMiddleware)
