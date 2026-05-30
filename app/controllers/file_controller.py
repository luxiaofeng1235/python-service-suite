"""
============================================
文件上传接口控制器层
============================================
职责：只负责路由定义、接收请求、参数校验、返回响应。
业务逻辑全部委托给 FileService。
"""

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.common.response import Response
from app.core.config import settings
from app.core.dependency import get_current_user
from app.database import get_session
from app.schemas.file import AttachmentResponse
from app.common.pagination import PageParams
from app.services.file_service import FileService

router = APIRouter(prefix="/api/file", tags=["文件管理"])

CHUNK_SIZE = 64 * 1024  # 64 KB 分块读取


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
    ext = Path(file.filename or "image").suffix.lower()
    date_str = datetime.now().strftime("%Y/%m")
    stored_name = f"{uuid.uuid4().hex}{ext}"
    sub_path = f"images/{date_str}"
    upload_dir = Path(settings.UPLOAD_DIR) / sub_path
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / stored_name

    file_size = 0
    with open(file_path, "wb") as f:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            file_size += len(chunk)
            if file_size > settings.FILE_IMAGE_MAX_SIZE:
                file_path.unlink(missing_ok=True)
                raise AppException(
                    msg=f"图片大小超过限制（最大 {settings.FILE_IMAGE_MAX_SIZE // 1024 // 1024} MB）"
                )
            f.write(chunk)

    attachment = await FileService.upload_image_from_path(
        db=db,
        user_id=0,
        original_name=file.filename or "unknown",
        mime_type=file.content_type or "application/octet-stream",
        stored_path=str(Path(sub_path) / stored_name),
        file_size=file_size,
    )
    data = AttachmentResponse.from_orm(attachment, str(request.base_url))
    return Response.success(data, msg="图片上传成功")


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
    ext = Path(file.filename or "video").suffix.lower()
    date_str = datetime.now().strftime("%Y/%m")
    stored_name = f"{uuid.uuid4().hex}{ext}"
    sub_path = f"videos/{date_str}"
    upload_dir = Path(settings.UPLOAD_DIR) / sub_path
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / stored_name

    file_size = 0
    with open(file_path, "wb") as f:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            file_size += len(chunk)
            if file_size > settings.FILE_VIDEO_MAX_SIZE:
                file_path.unlink(missing_ok=True)
                raise AppException(
                    msg=f"视频大小超过限制（最大 {settings.FILE_VIDEO_MAX_SIZE // 1024 // 1024} MB）"
                )
            f.write(chunk)

    attachment = await FileService.upload_video_from_path(
        db=db,
        user_id=0,
        original_name=file.filename or "unknown",
        mime_type=file.content_type or "application/octet-stream",
        stored_path=str(Path(sub_path) / stored_name),
        file_size=file_size,
    )
    data = AttachmentResponse.from_orm(attachment, str(request.base_url))
    return Response.success(data, msg="视频上传成功")


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
    # data["items"] 是 ORM 对象列表：[ORM1, ORM2, ...]
    # 用列表推导遍历每个 ORM 对象，逐个通过 from_orm 拼出完整 url
    # from_orm 只处理单个对象，循环由外面的列表推导负责
    items = [
        AttachmentResponse.from_orm(item, str(request.base_url))
        for item in data["items"]
    ]
    return Response.success(
        {"items": items, "total": data["total"], "page": data["page"], "size": data["size"]}
    )
