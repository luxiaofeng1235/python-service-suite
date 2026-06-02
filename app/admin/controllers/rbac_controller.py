"""
============================================
RBAC 管理控制器层
============================================
提供权限目录管理、角色 CRUD、权限分配、用户-角色绑定的管理接口。
RBAC 管理路由使用 require_permission（超管直通，角色用户按权限访问）。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import Response
from app.core.rbac import require_permission
from app.database import get_session
from app.schemas.rbac import (
    PermissionAssignRequest,
    PermissionCreateRequest,
    RoleCreateRequest,
    RoleUpdateRequest,
    UserRoleRequest,
)
from app.services.rbac_service import RbacService

router = APIRouter(prefix="/admin", tags=["后台-RBAC 权限管理"])


# ==================== 权限目录管理 ====================


@router.get(
    "/permissions",
    summary="权限目录列表",
    dependencies=[Depends(require_permission("permission", "list"))],
)
async def list_permissions(
    db: AsyncSession = Depends(get_session),
):
    """获取权限目录（管理后台下拉菜单用）"""
    perms = await RbacService.list_permissions(db)
    return Response.success(perms)


@router.post(
    "/permissions",
    summary="创建权限目录条目",
    dependencies=[Depends(require_permission("permission", "create"))],
)
async def create_permission(
    req: PermissionCreateRequest,
    db: AsyncSession = Depends(get_session),
):
    """新增一条可分配的权限"""
    perm = await RbacService.create_permission(
        db, resource=req.resource, action=req.action, description=req.description,
    )
    return Response.success(perm, msg="权限创建成功")


@router.delete(
    "/permissions/{permission_id}",
    summary="删除权限目录条目",
    dependencies=[Depends(require_permission("permission", "delete"))],
)
async def delete_permission(
    permission_id: int,
    db: AsyncSession = Depends(get_session),
):
    """删除权限目录条目"""
    await RbacService.delete_permission(db, permission_id)
    return Response.success(msg="权限删除成功")


# ==================== 角色管理 ====================


@router.post(
    "/roles",
    summary="创建角色",
    dependencies=[Depends(require_permission("role", "create"))],
)
async def create_role(
    req: RoleCreateRequest,
    db: AsyncSession = Depends(get_session),
):
    """创建新角色"""
    role = await RbacService.create_role(db, name=req.name, description=req.description)
    return Response.success(role, msg="角色创建成功")


@router.get(
    "/roles",
    summary="角色列表",
    dependencies=[Depends(require_permission("role", "list"))],
)
async def list_roles(
    db: AsyncSession = Depends(get_session),
):
    """获取所有角色列表"""
    roles = await RbacService.list_roles(db)
    return Response.success(roles)


@router.get(
    "/roles/{role_id}",
    summary="角色详情",
    dependencies=[Depends(require_permission("role", "read"))],
)
async def get_role(
    role_id: int,
    db: AsyncSession = Depends(get_session),
):
    """获取角色详情"""
    role = await RbacService.get_role_by_id(db, role_id)
    return Response.success(role)


@router.put(
    "/roles/{role_id}",
    summary="更新角色",
    dependencies=[Depends(require_permission("role", "update"))],
)
async def update_role(
    role_id: int,
    req: RoleUpdateRequest,
    db: AsyncSession = Depends(get_session),
):
    """更新角色信息"""
    role = await RbacService.update_role(
        db, role_id, name=req.name, description=req.description,
    )
    return Response.success(role, msg="更新成功")


@router.delete(
    "/roles/{role_id}",
    summary="删除角色",
    dependencies=[Depends(require_permission("role", "delete"))],
)
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_session),
):
    """删除角色（系统内置角色不可删除）"""
    await RbacService.delete_role(db, role_id)
    return Response.success(msg="删除成功")


# ==================== 权限分配 ====================


@router.get(
    "/roles/{role_id}/permissions",
    summary="角色权限列表",
    dependencies=[Depends(require_permission("permission", "list"))],
)
async def get_role_permissions(
    role_id: int,
    db: AsyncSession = Depends(get_session),
):
    """获取角色的所有权限（含中文描述）"""
    perms = await RbacService.get_role_permissions(db, role_id)
    return Response.success(perms)


@router.post(
    "/roles/{role_id}/permissions",
    summary="为角色分配权限",
    dependencies=[Depends(require_permission("permission", "assign"))],
)
async def add_role_permission(
    role_id: int,
    req: PermissionAssignRequest,
    db: AsyncSession = Depends(get_session),
):
    """为角色分配一条权限（需先在权限目录中存在）"""
    await RbacService.add_role_permission(db, role_id, req.resource, req.action)
    return Response.success(msg="权限添加成功")


@router.delete(
    "/roles/{role_id}/permissions",
    summary="移除角色权限",
    dependencies=[Depends(require_permission("permission", "assign"))],
)
async def remove_role_permission(
    role_id: int,
    req: PermissionAssignRequest,
    db: AsyncSession = Depends(get_session),
):
    """移除角色的一条权限"""
    await RbacService.remove_role_permission(db, role_id, req.resource, req.action)
    return Response.success(msg="权限移除成功")


# ==================== 用户-角色绑定 ====================


@router.get(
    "/admins/{admin_id}/roles",
    summary="管理员的角色列表",
    dependencies=[Depends(require_permission("user_role", "list"))],
)
async def get_admin_roles(
    admin_id: int,
    db: AsyncSession = Depends(get_session),
):
    """获取管理员的所有角色"""
    roles = await RbacService.get_user_roles(db, admin_id)
    return Response.success(roles)


@router.post(
    "/admins/{admin_id}/roles",
    summary="为管理员分配角色",
    dependencies=[Depends(require_permission("user_role", "assign"))],
)
async def assign_admin_role(
    admin_id: int,
    req: UserRoleRequest,
    db: AsyncSession = Depends(get_session),
):
    """为管理员分配一个角色"""
    await RbacService.assign_user_role(db, admin_id, req.role_id)
    return Response.success(msg="角色分配成功")


@router.delete(
    "/admins/{admin_id}/roles/{role_id}",
    summary="移除管理员的角色",
    dependencies=[Depends(require_permission("user_role", "assign"))],
)
async def remove_admin_role(
    admin_id: int,
    role_id: int,
    db: AsyncSession = Depends(get_session),
):
    """移除管理员的一个角色"""
    await RbacService.remove_user_role(db, admin_id, role_id)
    return Response.success(msg="角色移除成功")
