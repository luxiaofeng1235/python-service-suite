"""
============================================
后台管理控制器层
============================================
"""

from app.admin.controllers import (
    admin_controller,
    auth_controller,
    cms_article_controller,
    rbac_controller,
    user_admin_controller,
)

__all__ = [
    "admin_controller",
    "auth_controller",
    "cms_article_controller",
    "rbac_controller",
    "user_admin_controller",
]
