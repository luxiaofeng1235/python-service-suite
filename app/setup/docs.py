"""
============================================
自定义文档页面注册
============================================
"""

from fastapi import FastAPI
from fastapi.openapi.docs import get_redoc_html

from app.core.config import settings


def register_docs(app: FastAPI) -> None:
    """注册自定义 ReDoc 文档页面（固定 CDN 版本）"""

    @app.get("/redoc", include_in_schema=False)
    async def redoc_html():
        return get_redoc_html(
            openapi_url="/openapi.json",
            title=f"{settings.PROJECT_NAME} - ReDoc",
            redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@2.5.3/bundles/redoc.standalone.js",
        )
