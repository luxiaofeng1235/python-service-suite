"""
============================================
路由聚合包
============================================
统一导出 api_router 和 admin_router，让 setup/routes.py 一站式注册。
"""

from app.routes.admin import admin_router
from app.routes.api import api_router

__all__ = ["admin_router", "api_router"]
