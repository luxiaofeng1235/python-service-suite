"""
============================================
路由聚合包
============================================
统一导出 api_router，main.py 只需注册一次。
"""

from app.routes.api import api_router

__all__ = ["api_router"]
