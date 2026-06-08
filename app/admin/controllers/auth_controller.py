"""
============================================
后台管理员认证控制器层
============================================
提供管理员登录、退出、个人信息查看接口。
路由前缀 /admin/auth，完全独立于前台 /api/user/ 体系。
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.services.auth_service import AdminAuthService
from app.common.exception import AppException
from app.common.ratelimit import RateLimiter
from app.common.response import Response
from app.core.admin_auth import get_current_admin_user
from app.core.rbac import require_permission
from app.database import get_session
from app.schemas.auth_admin import AdminLoginRequest, AdminRegisterRequest

# 速率限制器
_admin_login_limiter = RateLimiter(max_requests=5, window_seconds=300)  # 后台登录：5次/5分钟

router = APIRouter(prefix="/admin/auth", tags=["后台-管理员认证"])


@router.post("/login", summary="管理员登录")
async def login(
    req: AdminLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    """
    管理员登录接口

    - 使用 auth_admins 表中的账号密码
    - 签发独立的后台 Token
    """
    client_ip = request.client.host if request.client else "unknown"
    if not await _admin_login_limiter.check(f"admin_login:{client_ip}:{req.username}"):
        raise AppException(msg="登录过于频繁，请 5 分钟后再试")

    token = await AdminAuthService.authenticate(db, req.username, req.password)
    return Response.success(
        data={"access_token": token, "token_type": "bearer"},
        msg="登录成功",
    )


@router.post(
    "/register",
    summary="创建管理员（需超管）",
    dependencies=[Depends(require_permission("admin", "create"))],
)
async def register(
    req: AdminRegisterRequest,
    db: AsyncSession = Depends(get_session),
):
    """超管创建新的后台管理员"""
    admin = await AdminAuthService.register(db, req.username, req.password, req.nickname)
    return Response.success(
        data={"id": admin.id, "username": admin.username, "nickname": admin.nickname},
        msg="管理员创建成功",
    )


@router.post("/logout", summary="管理员退出登录")
async def logout(
    db: AsyncSession = Depends(get_session),
    current_admin: dict = Depends(get_current_admin_user),
):
    """退出登录，使当前 Token 立即失效"""
    data = await AdminAuthService.logout(db, current_admin["token_id"])
    return Response.success(data=data, msg="退出成功")


@router.get("/info", summary="当前管理员信息")
async def get_me(
    db: AsyncSession = Depends(get_session),
    current_admin: dict = Depends(get_current_admin_user),
):
    """获取当前登录的管理员完整信息"""
    admin = await AdminAuthService.get_admin_info(db, current_admin["user_id"])
    return Response.success(data=admin)
