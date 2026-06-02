"""
============================================
文件上传接口控制器层
============================================
职责：只负责路由定义、接收请求、参数校验、返回响应。
业务逻辑全部委托给 FileService。
"""

from fastapi import APIRouter, Depends, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import Response
from app.database import get_session
from app.schemas.file import AttachmentResponse
from app.common.pagination import PageParams
from app.api.services.file_service import FileService

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
    attachment = await FileService.upload_image_stream(db, user_id=0, file=file)
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
    attachment = await FileService.upload_video_stream(db, user_id=0, file=file)
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
    items = [
        AttachmentResponse.from_orm(item, str(request.base_url))
        for item in data["items"]
    ]
    file_list = {
        "items": items,  # 文件列表
        "total": data["total"],  # 记录集总数
        "total_page": data["page"],  # 总页数
        "size": data["size"],  # 步长
    }
    return Response.success(file_list, "文件列表")
