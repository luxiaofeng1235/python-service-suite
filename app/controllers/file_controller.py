"""
============================================
文件上传接口控制器层
============================================
职责：只负责路由定义、接收请求、参数校验、返回响应。
业务逻辑全部委托给 FileService。
"""

from fastapi import APIRouter, Depends, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import Response
from app.core.dependency import get_current_user
from app.database import get_session
from app.schemas.file import AttachmentResponse
from app.services.file_service import FileService

router = APIRouter(prefix="/api/file", tags=["文件管理"])


# ==================== 图片上传 ====================


@router.post("/upload/image", summary="上传图片")
async def upload_image(
    file: UploadFile,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """
    上传图片文件

    - 支持格式：从配置读取
    - 最大大小：从配置读取（默认 10 MB）
    - 需登录
    """
    try:
        file_data = await file.read()
        attachment = await FileService.upload_image(
            db=db,
            user_id=current_user["user_id"],
            file_data=file_data,
            original_name=file.filename or "unknown",
            mime_type=file.content_type or "application/octet-stream",
        )
        data = AttachmentResponse(
            id=attachment.id,
            original_name=attachment.original_name,
            stored_name=attachment.stored_name,
            file_path=attachment.file_path,
            file_size=attachment.file_size,
            mime_type=attachment.mime_type,
            file_type=attachment.file_type,
            url=FileService.get_file_url(attachment.file_path),
            created_at=attachment.created_at.isoformat() if attachment.created_at else None,
        )
        return Response.success(data, msg="图片上传成功")
    except ValueError as e:
        return Response.fail(msg=str(e))


# ==================== 视频上传 ====================


@router.post("/upload/video", summary="上传视频")
async def upload_video(
    file: UploadFile,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """
    上传视频文件

    - 支持格式：从配置读取
    - 最大大小：从配置读取（默认 200 MB）
    - 需登录
    """
    try:
        file_data = await file.read()
        attachment = await FileService.upload_video(
            db=db,
            user_id=current_user["user_id"],
            file_data=file_data,
            original_name=file.filename or "unknown",
            mime_type=file.content_type or "application/octet-stream",
        )
        data = AttachmentResponse(
            id=attachment.id,
            original_name=attachment.original_name,
            stored_name=attachment.stored_name,
            file_path=attachment.file_path,
            file_size=attachment.file_size,
            mime_type=attachment.mime_type,
            file_type=attachment.file_type,
            url=FileService.get_file_url(attachment.file_path),
            created_at=attachment.created_at.isoformat() if attachment.created_at else None,
        )
        return Response.success(data, msg="视频上传成功")
    except ValueError as e:
        return Response.fail(msg=str(e))


# ==================== 文件列表 ====================


@router.get("/list", summary="文件列表（分页）")
async def list_files(
    file_type: str | None = Query(None, description="筛选文件类型：image / video"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(10, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """
    获取当前用户上传的文件列表

    - 可选按文件类型筛选
    - 分页查询，默认每页 10 条
    - 只能看到自己的文件
    """
    data = await FileService.get_file_list(
        db,
        user_id=current_user["user_id"],
        file_type=file_type,
        page=page,
        size=size,
    )
    items = [
        AttachmentResponse(
            id=item.id,
            original_name=item.original_name,
            stored_name=item.stored_name,
            file_path=item.file_path,
            file_size=item.file_size,
            mime_type=item.mime_type,
            file_type=item.file_type,
            url=FileService.get_file_url(item.file_path),
            created_at=item.created_at.isoformat() if item.created_at else None,
        )
        for item in data["items"]
    ]
    return Response.success(
        {"items": items, "total": data["total"], "page": data["page"], "size": data["size"]}
    )
