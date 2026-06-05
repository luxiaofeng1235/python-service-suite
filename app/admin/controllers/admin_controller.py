"""
============================================
后台管理员账号管理控制器层
============================================
提供管理员的列表、禁用/启用切换等功能。
路由前缀 /admin/admins，独立于前台用户管理。
"""

from fastapi import APIRouter, Depends, UploadFile, File
from pathlib import Path
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.services.auth_service import AdminAuthService
from app.common.response import Response
from app.core.admin_auth import get_current_admin_user
from app.core.rbac import require_permission
from app.database import get_session
from app.models.auth_admin import AuthAdmin
from app.schemas.auth_admin import AdminProfileUpdateRequest
from app.storage.local import ensure_upload_dir, generate_stored_name
from app.storage.validation import validate_image, IMAGE_MAX_SIZE

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
    """管理员修改自己的资料（昵称、手机号、邮箱、性别、备注）"""
    admin_id = current_admin["user_id"]
    result = await db.execute(select(AuthAdmin).where(AuthAdmin.id == admin_id))
    admin = result.scalar_one_or_none()
    if not admin:
        return Response.fail(msg="管理员不存在")

    update_data = req.model_dump(exclude_none=True)
    if not update_data:
        return Response.fail(msg="没有需要修改的字段")

    for field, value in update_data.items():
        setattr(admin, field, value)
    await db.commit()
    await db.refresh(admin)
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
    """上传管理员头像（支持 jpg/png/gif/webp，最大 5MB）"""
    # 1. 校验文件
    ext = Path(file.filename or "image.jpg").suffix.lower()
    file_data = await file.read()
    file_size = len(file_data)
    validate_image(ext, file_size)

    # 2. 存储文件
    date_str = datetime.now().strftime("%Y/%m")
    stored_name, _, _ = generate_stored_name(file.filename or "avatar.jpg")
    sub_path = f"avatars/{date_str}"
    upload_dir = ensure_upload_dir(sub_path)
    file_path = upload_dir / stored_name
    with open(file_path, "wb") as f:
        f.write(file_data)

    # 3. 更新数据库
    avatar_url = f"/uploads/{sub_path}/{stored_name}"
    admin_id = current_admin["user_id"]
    result = await db.execute(select(AuthAdmin).where(AuthAdmin.id == admin_id))
    admin = result.scalar_one_or_none()
    if admin:
        admin.avatar = avatar_url
        await db.commit()

    return Response.success(data={"avatar": avatar_url}, msg="头像上传成功")
