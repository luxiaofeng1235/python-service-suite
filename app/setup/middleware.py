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
    # 请求顺序：CORS → 404 归一化 → 验签 → 日志 → 路由。

    # 请求日志
    app.add_middleware(RequestLogMiddleware)

    # 验签通过后，将请求体交给日志和路由。
    if settings.API_ENCRYPT_ENABLED:
        app.add_middleware(ApiEncryptMiddleware)

    # 404 统一响应。
    app.add_middleware(NotFoundMiddleware)

    # CORS 包裹验签中间件，确保直接返回的 403 也带跨域响应头。
    origins = settings.CORS_ORIGINS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
