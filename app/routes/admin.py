"""
============================================
后台管理路由聚合
============================================
后续新增后台业务 controller 时，在此集中 include_router。
"""

from fastapi import APIRouter

from app.admin.controllers import (
    admin_controller,
    auth_controller,
    rbac_controller,
    user_admin_controller,
)

admin_router = APIRouter()

# 后台管理员认证
admin_router.include_router(auth_controller.router)

# 后台管理员账号管理
admin_router.include_router(admin_controller.router)

# 后台用户管理接口
admin_router.include_router(user_admin_controller.router)

# 后台 RBAC 权限管理接口
admin_router.include_router(rbac_controller.router)
