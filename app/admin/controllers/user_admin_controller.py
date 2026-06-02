"""
============================================
后台用户管理控制器层
============================================
职责：只负责路由定义、接收请求、参数校验、返回响应。
业务逻辑全部委托给 UserAdminService。

权限控制：
  - 业务接口使用 require_permission() — 超管直通，角色用户按权限访问
  - 禁用/启用接口独立为 dedicated 端点
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.user_admin import AdminUserUpdateRequest
from app.admin.services.user_admin_service import UserAdminService
from app.common.pagination import PageParams
from app.common.response import Response
from app.core.rbac import require_permission
from app.database import get_session

# ==================== 路由定义 ====================
router = APIRouter(prefix="/admin/users", tags=["后台-用户管理"])


# ==================== 用户列表 ====================


@router.get(
    "/list",
    summary="用户列表（后台）",
    dependencies=[Depends(require_permission("user", "list"))],
)
async def list_users(
    page_params: PageParams = Depends(),
    is_deleted: bool | None = Query(None, description="过滤已注销：None=全部, true=仅已注销, false=仅未注销"),
    db: AsyncSession = Depends(get_session),
):
    """
    获取用户列表（需 user:list 权限）

    - 分页查询，可筛选是否已注销
    - 返回比前台接口更多的字段
    """
    data = await UserAdminService.get_user_list(
        db,
        page_params=page_params,
        is_deleted=is_deleted,
    )
    return Response.success(data)


# ==================== 用户详情 ====================


@router.get(
    "/{user_id}",
    summary="用户详情（后台）",
    dependencies=[Depends(require_permission("user", "read"))],
)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_session),
):
    """
    获取用户详情（需 user:read 权限）

    包含 is_deleted、deleted_at 等前台不返回的字段。
    """
    data = await UserAdminService.get_user_by_id(db, user_id=user_id)
    return Response.success(data)


# ==================== 更新用户 ====================


@router.put(
    "/{user_id}",
    summary="更新用户（后台）",
    dependencies=[Depends(require_permission("user", "update"))],
)
async def update_user(
    user_id: int,
    req: AdminUserUpdateRequest,
    db: AsyncSession = Depends(get_session),
):
    """
    更新用户信息（需 user:update 权限）

    - 可修改 nickname / is_super / is_active
    """
    data = await UserAdminService.update_user(db, user_id=user_id, req=req)
    return Response.success(data, msg="更新成功")


# ==================== 删除用户 ====================


@router.delete(
    "/{user_id}",
    summary="强制注销用户（后台）",
    dependencies=[Depends(require_permission("user", "delete"))],
)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(require_permission("user", "delete")),
):
    """
    管理员强制注销用户（需 user:delete 权限）

    - 标记 is_deleted=True
    - 清空该用户所有 Token
    """
    data = await UserAdminService.delete_user(
        db,
        user_id=user_id,
        operator_username=current_user.get("username", "admin"),
    )
    return Response.success(data, msg="已强制注销")


# ==================== 禁用/启用 ====================


@router.post(
    "/{user_id}/disable",
    summary="禁用用户",
    dependencies=[Depends(require_permission("user", "disable"))],
)
async def disable_user(
    user_id: int,
    db: AsyncSession = Depends(get_session),
):
    """
    禁用用户账户（需 user:disable 权限）

    - 设置 is_active=False
    - 用户无法登录
    """
    data = await UserAdminService.set_user_active(db, user_id=user_id, is_active=False)
    return Response.success(data, msg="已禁用")


@router.post(
    "/{user_id}/enable",
    summary="启用用户",
    dependencies=[Depends(require_permission("user", "enable"))],
)
async def enable_user(
    user_id: int,
    db: AsyncSession = Depends(get_session),
):
    """
    启用用户账户（需 user:enable 权限）

    - 设置 is_active=True
    - 用户可以正常登录
    """
    data = await UserAdminService.set_user_active(db, user_id=user_id, is_active=True)
    return Response.success(data, msg="已启用")


# ==================== 清理过期 Token ====================


@router.post(
    "/tokens/cleanup",
    summary="清理过期 Token（后台）",
    dependencies=[Depends(require_permission("user", "cleanup"))],
)
async def cleanup_expired_tokens(
    db: AsyncSession = Depends(get_session),
):
    """
    清理所有过期 Token（需 user:cleanup 权限）
    """
    data = await UserAdminService.cleanup_expired_tokens(db)
    return Response.success(data, msg="清理成功")
