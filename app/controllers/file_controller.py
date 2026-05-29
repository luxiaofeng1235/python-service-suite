"""
============================================
文件上传接口控制器层
============================================
职责：只负责路由定义、接收请求、参数校验、返回响应。
业务逻辑全部委托给 FileService。
"""

from fastapi import APIRouter, Depends, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import Response
from app.core.dependency import get_current_user
from app.database import get_session
from app.schemas.file import AttachmentResponse
from app.common.pagination import PageParams
from app.services.file_service import FileService

router = APIRouter(prefix="/api/file", tags=["文件管理"])


# ==================== 图片上传 ====================


@router.post("/upload/image", summary="上传图片（无需登录）")
async def upload_image(
    file: UploadFile,
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    """
    上传图片文件

    - 支持格式：从配置读取
    - 最大大小：从配置读取（默认 10 MB）
    - 无需登录
    """
    try:
        file_data = await file.read()
        attachment = await FileService.upload_image(
            db=db,
            user_id=0,
            file_data=file_data,
            original_name=file.filename or "unknown",
            mime_type=file.content_type or "application/octet-stream",
        )
        data = AttachmentResponse.from_orm(attachment, str(request.base_url))
        return Response.success(data, msg="图片上传成功")
    except ValueError as e:
        return Response.fail(msg=str(e))


# ==================== 视频上传 ====================


@router.post("/upload/video", summary="上传视频（无需登录）")
async def upload_video(
    file: UploadFile,
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    """
    上传视频文件

    - 支持格式：从配置读取
    - 最大大小：从配置读取（默认 200 MB）
    - 无需登录
    """
    try:
        file_data = await file.read()
        attachment = await FileService.upload_video(
            db=db,
            user_id=0,
            file_data=file_data,
            original_name=file.filename or "unknown",
            mime_type=file.content_type or "application/octet-stream",
        )
        data = AttachmentResponse.from_orm(attachment, str(request.base_url))
        return Response.success(data, msg="视频上传成功")
    except ValueError as e:
        return Response.fail(msg=str(e))


# ==================== 文件列表 ====================


@router.get("/list", summary="文件列表（分页）")
async def list_files(
    request: Request,
    page_params: PageParams = Depends(),
    db: AsyncSession = Depends(get_session),
):
    """
    获取文件列表（无需登录）

    - 分页查询，默认每页 10 条
    - 返回全部文件
    """
    data = await FileService.get_file_list(
        db,
        user_id=None,
        page_params=page_params,
    )
    items = [
        AttachmentResponse.from_orm(item, str(request.base_url))
        for item in data["items"]
    ]
    return Response.success(
        {"items": items, "total": data["total"], "page": data["page"], "size": data["size"]}
    )
