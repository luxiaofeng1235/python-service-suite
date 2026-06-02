"""
============================================
后台管理员账号管理控制器层
============================================
提供管理员的列表、禁用/启用切换等功能。
路由前缀 /admin/admins，独立于前台用户管理。
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import Response
from app.core.admin_auth import get_current_admin_user
from app.core.rbac import require_permission
from app.database import get_session
from app.models.auth_admin import AuthAdmin

router = APIRouter(prefix="/admin/admins", tags=["后台-管理员管理"])


@router.get(
    "/list",
    summary="管理员列表",
    dependencies=[Depends(require_permission("admin", "list"))],
)
async def list_admins(db: AsyncSession = Depends(get_session)):
    """获取所有管理员账号列表"""
    result = await db.execute(
        select(AuthAdmin).order_by(AuthAdmin.id)
    )
    admins = result.scalars().all()
    return Response.success(admins)


@router.post(
    "/{admin_id}/toggle-active",
    summary="禁用/启用切换",
    dependencies=[Depends(require_permission("admin", "toggle"))],
)
async def toggle_admin_active(
    admin_id: int,
    db: AsyncSession = Depends(get_session),
    current_admin: dict = Depends(get_current_admin_user),
):
    """
    切换管理员启用/禁用状态

    保护规则：
      - 不能对自己操作
      - 不能禁用超管
    """
    # 不能对自己操作
    if current_admin["user_id"] == admin_id:
        return Response.fail(msg="不能对自己操作")

    result = await db.execute(select(AuthAdmin).where(AuthAdmin.id == admin_id))
    admin = result.scalar_one_or_none()
    if not admin:
        return Response.fail(msg="管理员不存在")

    # 不能禁用超管
    if admin.is_super:
        return Response.fail(msg="不能操作超管账号")

    admin.is_active = not admin.is_active
    status = "启用" if admin.is_active else "禁用"
    return Response.success(data={"is_active": admin.is_active}, msg=f"已{status}")
