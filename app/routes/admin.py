"""
============================================
后台管理路由聚合
============================================
后续新增后台业务 controller 时，在此集中 include_router。
"""

from fastapi import APIRouter
from starlette.responses import RedirectResponse

from app.admin.controllers import (
    admin_controller,
    auth_controller,
    cms_article_controller,
    rbac_controller,
    user_admin_controller,
)

admin_router = APIRouter()


# /admin → 跳转登录页（避免直接 Not Found）
@admin_router.get("/admin", include_in_schema=False)
@admin_router.get("/admin/", include_in_schema=False)
async def admin_root():
    return RedirectResponse(url="/admin/auth/login")

# /admin/auth/login → GET 返回接口说明，避免 405
@admin_router.get("/admin/auth/login", include_in_schema=False)
async def admin_login_page():
    return {
        "msg": "该接口仅接受 POST 请求，请在 Swagger 文档中调试",
        "docs": "/docs",
        "endpoint": "POST /admin/auth/login",
        "params": {"username": "string", "password": "string"},
    }


# 后台管理员认证
admin_router.include_router(auth_controller.router)

# 后台管理员账号管理
admin_router.include_router(admin_controller.router)

# 后台用户管理接口
admin_router.include_router(user_admin_controller.router)

# 后台 RBAC 权限管理接口
admin_router.include_router(rbac_controller.router)

# 后台 CMS 文章管理接口
admin_router.include_router(cms_article_controller.router)
