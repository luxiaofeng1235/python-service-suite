"""
============================================
后台管理员账号管理控制器层
============================================
提供管理员的列表、禁用/启用切换等功能。
路由前缀 /admin/admins，独立于前台用户管理。
"""

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.services.auth_service import AdminAuthService
from app.api.services.file_service import FileService
from app.common.response import Response
from app.core.admin_auth import get_current_admin_user
from app.core.rbac import require_permission
from app.database import get_session
from app.models.auth_admin import AuthAdmin
from app.schemas.auth_admin import AdminProfileUpdateRequest

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
    await db.commit()
    await db.refresh(admin)
    status = "启用" if admin.is_active else "禁用"
    return Response.success(data={"is_active": admin.is_active}, msg=f"已{status}")


@router.put(
    "/profile",
    summary="修改个人资料",
    dependencies=[Depends(get_current_admin_user)],
)
async def update_profile(
    req: AdminProfileUpdateRequest,
    db: AsyncSession = Depends(get_session),
    current_admin: dict = Depends(get_current_admin_user),
):
    """管理员修改自己的资料"""
    update_data = req.model_dump(exclude_none=True)
    if not update_data:
        return Response.fail(msg="没有需要修改的字段")

    admin = await AdminAuthService.update_profile(db, current_admin["user_id"], update_data)
    return Response.success(admin, msg="修改成功")


@router.post(
    "/avatar",
    summary="上传头像",
    dependencies=[Depends(get_current_admin_user)],
)
async def upload_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    current_admin: dict = Depends(get_current_admin_user),
):
    """上传管理员头像"""
    attachment = await FileService.upload_image_stream(db, user_id=0, file=file)
    avatar_url = FileService.get_file_url(attachment.file_path)
    await AdminAuthService.update_avatar(db, current_admin["user_id"], avatar_url)
    return Response.success(data={"avatar": avatar_url}, msg="头像上传成功")
