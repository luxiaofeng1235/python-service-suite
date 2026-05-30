"""
============================================
路由 & 静态文件挂载注册
============================================
"""

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes import api_router
from app.core.config import settings


def register_routes(app: FastAPI) -> None:
    """注册所有业务路由"""
    app.include_router(api_router)


def register_static_files(app: FastAPI) -> None:
    """挂载上传文件静态目录"""
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


def register_root_route(app: FastAPI) -> None:
    """注册根路径路由"""

    @app.get("/", tags=["基础"])
    async def root():
        """根路径，重定向到文档"""
        return {"message": f"欢迎使用 {settings.PROJECT_NAME}", "docs": "/docs"}
