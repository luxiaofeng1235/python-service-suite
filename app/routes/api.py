"""
============================================
API 路由聚合
============================================
后续新增业务 controller 时，在此集中 include_router。
"""

from fastapi import APIRouter

from app.controllers import ai_controller, user_controller

api_router = APIRouter()

# 用户模块接口
api_router.include_router(user_controller.router)

# AI 服务接口
api_router.include_router(ai_controller.router)
