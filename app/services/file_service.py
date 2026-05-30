"""
============================================
文件上传业务逻辑层
============================================
职责：文件存储、数据库记录写入、文件类型校验、大小校验。
不在本层做任何路由/请求相关的操作。
"""

import os
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.common.pagination import PageParams, paginate
from app.core.config import settings
from app.models.attachment import Attachment


# ==================== 支持的格式与大小限制（从配置读取）====================

def _image_extensions() -> set[str]:
    """允许的图片扩展名（带点前缀）"""
    return {"." + ext for ext in settings.FILE_IMAGE_EXTENSIONS}


def _video_extensions() -> set[str]:
    """允许的视频扩展名（带点前缀）"""
    return {"." + ext for ext in settings.FILE_VIDEO_EXTENSIONS}


IMAGE_EXTENSIONS: set[str] = _image_extensions()
VIDEO_EXTENSIONS: set[str] = _video_extensions()
IMAGE_MAX_SIZE: int = settings.FILE_IMAGE_MAX_SIZE
VIDEO_MAX_SIZE: int = settings.FILE_VIDEO_MAX_SIZE


class FileService:
    """文件上传业务逻辑"""

    @staticmethod
    def _get_file_type(ext: str) -> str:
        """根据扩展名判断文件分类"""
        ext = ext.lower()
        if ext in IMAGE_EXTENSIONS:
            return "image"
        if ext in VIDEO_EXTENSIONS:
            return "video"
        return "other"

    @staticmethod
    def _validate_image(ext: str, file_size: int) -> None:
        """校验图片格式与大小"""
        if ext not in IMAGE_EXTENSIONS:
            raise AppException(msg=f"不支持的图片格式：{ext}，仅支持 {', '.join(sorted(IMAGE_EXTENSIONS))}")
        if file_size > IMAGE_MAX_SIZE:
            raise AppException(msg=f"图片大小超过限制（最大 {IMAGE_MAX_SIZE // 1024 // 1024} MB）")

    @staticmethod
    def _validate_video(ext: str, file_size: int) -> None:
        """校验视频格式与大小"""
        if ext not in VIDEO_EXTENSIONS:
            raise AppException(msg=f"不支持的视频格式：{ext}，仅支持 {', '.join(sorted(VIDEO_EXTENSIONS))}")
        if file_size > VIDEO_MAX_SIZE:
            raise AppException(msg=f"视频大小超过限制（最大 {VIDEO_MAX_SIZE // 1024 // 1024} MB）")

    @staticmethod
    def _ensure_upload_dir(sub_dir: str) -> Path:
        """确保上传子目录存在并返回 Path 对象"""
        upload_path = Path(settings.UPLOAD_DIR) / sub_dir
        upload_path.mkdir(parents=True, exist_ok=True)
        return upload_path

    @staticmethod
    def _generate_stored_name(original_name: str) -> tuple[str, str, str]:
        """生成存储文件名

        Returns:
            (stored_name, ext, stored_filename)
        """
        ext = Path(original_name).suffix.lower()
        stored_name = f"{uuid.uuid4().hex}{ext}"
        return stored_name, ext, stored_name

    @classmethod
    async def upload_image(
        cls,
        db: AsyncSession,
        user_id: int,
        file_data: bytes,
        original_name: str,
        mime_type: str,
    ) -> Attachment:
        """上传图片（接收完整字节数据）"""
        ext = Path(original_name).suffix.lower()
        file_size = len(file_data)

        # 校验
        cls._validate_image(ext, file_size)

        # 确定存储路径
        date_str = datetime.now().strftime("%Y/%m")
        stored_name, _, _ = cls._generate_stored_name(original_name)
        sub_path = f"images/{date_str}"
        upload_dir = cls._ensure_upload_dir(sub_path)
        file_path = upload_dir / stored_name

        # 写入文件
        file_path.write_bytes(file_data)

        # 数据库记录
        return await cls._create_attachment(
            db=db,
            user_id=user_id,
            original_name=original_name,
            stored_name=stored_name,
            file_path=str(Path(sub_path) / stored_name),
            file_size=file_size,
            mime_type=mime_type,
            file_type="image",
        )

    @classmethod
    async def upload_image_from_path(
        cls,
        db: AsyncSession,
        user_id: int,
        original_name: str,
        mime_type: str,
        stored_path: str,
        file_size: int,
    ) -> Attachment:
        """上传图片（文件已由调用方流式写入磁盘）

        Args:
            db: 数据库会话
            user_id: 上传用户 ID
            original_name: 原始文件名
            mime_type: MIME 类型
            stored_path: 已写入磁盘的相对路径
            file_size: 文件大小（字节）
        """
        ext = Path(original_name).suffix.lower()
        cls._validate_image(ext, file_size)
        return await cls._create_attachment(
            db=db,
            user_id=user_id,
            original_name=original_name,
            stored_name=Path(stored_path).name,
            file_path=stored_path,
            file_size=file_size,
            mime_type=mime_type,
            file_type="image",
        )

    @classmethod
    async def upload_video(
        cls,
        db: AsyncSession,
        user_id: int,
        file_data: bytes,
        original_name: str,
        mime_type: str,
    ) -> Attachment:
        """上传视频（接收完整字节数据）"""
        ext = Path(original_name).suffix.lower()
        file_size = len(file_data)

        # 校验
        cls._validate_video(ext, file_size)

        # 确定存储路径
        date_str = datetime.now().strftime("%Y/%m")
        stored_name, _, _ = cls._generate_stored_name(original_name)
        sub_path = f"videos/{date_str}"
        upload_dir = cls._ensure_upload_dir(sub_path)
        file_path = upload_dir / stored_name

        # 写入文件
        file_path.write_bytes(file_data)

        # 数据库记录
        return await cls._create_attachment(
            db=db,
            user_id=user_id,
            original_name=original_name,
            stored_name=stored_name,
            file_path=str(Path(sub_path) / stored_name),
            file_size=file_size,
            mime_type=mime_type,
            file_type="video",
        )

    @classmethod
    async def upload_video_from_path(
        cls,
        db: AsyncSession,
        user_id: int,
        original_name: str,
        mime_type: str,
        stored_path: str,
        file_size: int,
    ) -> Attachment:
        """上传视频（文件已由调用方流式写入磁盘）

        Args:
            db: 数据库会话
            user_id: 上传用户 ID
            original_name: 原始文件名
            mime_type: MIME 类型
            stored_path: 已写入磁盘的相对路径
            file_size: 文件大小（字节）
        """
        ext = Path(original_name).suffix.lower()
        cls._validate_video(ext, file_size)
        return await cls._create_attachment(
            db=db,
            user_id=user_id,
            original_name=original_name,
            stored_name=Path(stored_path).name,
            file_path=stored_path,
            file_size=file_size,
            mime_type=mime_type,
            file_type="video",
        )

    @classmethod
    async def _create_attachment(
        cls,
        db: AsyncSession,
        user_id: int,
        original_name: str,
        stored_name: str,
        file_path: str,
        file_size: int,
        mime_type: str,
        file_type: str,
    ) -> Attachment:
        """创建附件数据库记录"""
        attachment = Attachment(
            user_id=user_id,
            original_name=original_name,
            stored_name=stored_name,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            file_type=file_type,
        )
        db.add(attachment)
        await db.flush()
        await db.refresh(attachment)
        return attachment

    # ==================== 文件列表查询 ====================

    @staticmethod
    async def get_file_list(
        db: AsyncSession,
        page_params: PageParams,
        user_id: int | None = None,
    ) -> dict:
        """获取文件列表（分页）

        Args:
            db: 数据库会话
            user_id: 筛选上传用户（None 查全部）
            page: 页码
            size: 每页条数

        Returns:
            {"items": [...], "total": int, "page": int, "size": int}
        """
        query = select(Attachment)
        count_query = select(func.count(Attachment.id))

        if user_id is not None:
            query = query.where(Attachment.user_id == user_id)
            count_query = count_query.where(Attachment.user_id == user_id)

        query = query.order_by(Attachment.created_at.desc())

        return await paginate(db, query, page_params, count_query)

    @staticmethod
    def get_file_url(file_path: str, base_url: str = "") -> str:
        """根据文件相对路径生成完整访问 URL

        Args:
            file_path: 文件相对路径
            base_url: 当前请求的基础 URL（例如 http://localhost:8000/），
                      不传则返回相对路径
        """
        if base_url:
            base_url = base_url.rstrip("/")
            return f"{base_url}/uploads/{file_path}"
        return f"/uploads/{file_path}"
