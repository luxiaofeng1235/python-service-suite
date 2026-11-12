"""
============================================
路由 & 静态文件挂载注册
============================================
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.common.view import display
from app.core.config import settings
from app.routes import admin_router, api_router


def register_routes(app: FastAPI) -> None:
    """注册所有业务路由（前台 /api/* + 后台 /admin/*）"""
    app.include_router(api_router)
    app.include_router(admin_router)


def register_static_files(app: FastAPI) -> None:
    """挂载上传文件和公开静态资源目录"""
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
    public_dir = Path(__file__).resolve().parents[2] / "public"
    app.mount("/public", StaticFiles(directory=public_dir), name="public")


def register_root_route(app: FastAPI) -> None:
    """注册根路径路由"""

    @app.get("/", tags=["基础"], response_class=HTMLResponse)
    async def root(request: Request) -> HTMLResponse:
        """根路径居中展示项目介绍图片"""
        return display(request, "index.html", {"title": settings.PROJECT_NAME})
