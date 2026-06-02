"""
============================================
中间件注册
============================================
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.middleware.request_log import RequestLogMiddleware
from app.middleware.encrypt import ApiEncryptMiddleware
from app.core.config import settings


def register_middleware(app: FastAPI) -> None:
    """注册中间件（按执行顺序：加密 → 日志 → CORS）"""
    # 请求加解密（优先执行，解密后的 body 传给后续中间件）
    if settings.API_ENCRYPT_ENABLED:
        app.add_middleware(ApiEncryptMiddleware)

    # 请求日志
    app.add_middleware(RequestLogMiddleware)

    # CORS
    origins = settings.CORS_ORIGINS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
