"""
============================================
中间件注册
============================================
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.middleware.request_log import RequestLogMiddleware
from app.core.config import settings


def register_middleware(app: FastAPI) -> None:
    """注册 CORS 和请求日志中间件"""
    app.add_middleware(RequestLogMiddleware)
    origins = settings.CORS_ORIGINS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
