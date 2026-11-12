"""
============================================
文件上传接口控制器层
============================================
职责：只负责路由定义、接收请求、参数校验、返回响应。
业务逻辑全部委托给 FileService。
"""

from fastapi import APIRouter, Depends, Form, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.services.file_service import FileService
from app.common.exception import AppException
from app.common.pagination import PageParams
from app.common.response import Response
from app.database import get_session
from app.schemas.file import AttachmentResponse, OSSUploadResponse

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
    attachment = await FileService.upload_image_stream_for_owner(
        db,
        owner_type="user",
        owner_id=0,
        file=file,
    )
    data = AttachmentResponse.from_attachment(attachment, str(request.base_url))
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
    attachment = await FileService.upload_video_stream_for_owner(
        db,
        owner_type="user",
        owner_id=0,
        file=file,
    )
    data = AttachmentResponse.from_attachment(attachment, str(request.base_url))
    return Response.success(data, msg="视频上传成功")


# ==================== OSS 上传 ====================


@router.post("/upload/oss", summary="上传附件到 OSS（支持本地和 URL，无需登录和验签）")
async def upload_oss(
    file: UploadFile | None = None,
    url: str | None = Form(None),
    upload_type: str = Form("local"),
    db: AsyncSession = Depends(get_session),
):
    """Upload an image or video to OSS through the public endpoint.

    Args:
        file: 本地文件上传（upload_type=local 时必须提供）
        url: 远程 URL 上传（upload_type=url 时必须提供）
        upload_type: 上传类型，local（本地）或 url（远程），默认 local

    Returns:
        附件信息（id, url, originName, fileSize 等）
    """
    # 1. 校验 upload_type 参数
    if upload_type not in ("local", "url"):
        raise AppException(msg="upload_type 必须为 local 或 url")

    # 2. 根据 upload_type 严格校验参数
    if upload_type == "local":
        # 本地上传模式
        if not file:
            raise AppException(msg="upload_type=local 时必须提供 file 参数")
        if url:
            raise AppException(msg="upload_type=local 时不应提供 url 参数")

        attachment = await FileService.upload_oss_for_owner(
            db,
            owner_type=FileService.OWNER_USER,
            owner_id=0,
            file=file,
        )
    else:  # upload_type == "url"
        # URL 上传模式
        if not url:
            raise AppException(msg="upload_type=url 时必须提供 url 参数")
        if file:
            raise AppException(msg="upload_type=url 时不应提供 file 参数")

        attachment = await FileService.upload_oss_from_url(
            db,
            owner_type=FileService.OWNER_USER,
            owner_id=0,
            url=url,
        )

    data = OSSUploadResponse.model_validate(attachment).model_dump(mode="json", by_alias=True)
    return Response.success(data, msg="附件上传成功")


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
        AttachmentResponse.from_attachment(item, str(request.base_url)) for item in data["items"]
    ]
    return Response.success({**data, "items": items}, "文件列表")
