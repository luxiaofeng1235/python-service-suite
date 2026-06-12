"""
============================================
文件上传业务逻辑层
============================================
职责：文件上传流程编排、数据库记录写入、文件列表查询、URL 生成。
不在本层做文件 I/O 和校验（委托给 storage 模块）。
"""

from datetime import datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PageParams, paginate
from app.models.attachment import Attachment
from app.storage.local import ensure_upload_dir, generate_stored_name, write_stream
from app.storage.validation import (
    IMAGE_MAX_SIZE,
    VIDEO_MAX_SIZE,
    validate_image,
    validate_video,
)


class FileService:
    """文件上传业务逻辑"""

    # ==================== 图片上传（字节数据）====================

    @classmethod
    async def upload_image(
        cls,
        db: AsyncSession,
        user_id: int,
        file_data: bytes,
        original_name: str,
        mime_type: str,
        owner_type: str = "user",
        owner_id: int | None = None,
    ) -> Attachment:
        """上传图片（接收完整字节数据）"""
        ext = Path(original_name).suffix.lower()
        file_size = len(file_data)

        # 1. 校验文件格式和大小
        validate_image(ext, file_size)

        # 2. 确定存储路径（按日期分目录，避免单目录文件过多）
        date_str = datetime.now().strftime("%Y/%m")
        stored_name, _, _ = generate_stored_name(original_name)
        sub_path = f"images/{date_str}"
        upload_dir = ensure_upload_dir(sub_path)
        file_path = upload_dir / stored_name

        # 3. 写入文件到磁盘
        file_path.write_bytes(file_data)

        # 4. 写入数据库记录
        return await cls._create_attachment(
            db=db,
            user_id=user_id,
            owner_type=owner_type,
            owner_id=owner_id,
            original_name=original_name,
            stored_name=stored_name,
            file_path=f"{sub_path}/{stored_name}",
            file_size=file_size,
            mime_type=mime_type,
            file_type="image",
        )

    # ==================== 视频上传（字节数据）====================

    @classmethod
    async def upload_video(
        cls,
        db: AsyncSession,
        user_id: int,
        file_data: bytes,
        original_name: str,
        mime_type: str,
        owner_type: str = "user",
        owner_id: int | None = None,
    ) -> Attachment:
        """上传视频（接收完整字节数据）"""
        ext = Path(original_name).suffix.lower()
        file_size = len(file_data)

        # 1. 校验文件格式和大小
        validate_video(ext, file_size)

        # 2. 确定存储路径（按日期分目录，避免单目录文件过多）
        date_str = datetime.now().strftime("%Y/%m")
        stored_name, _, _ = generate_stored_name(original_name)
        sub_path = f"videos/{date_str}"
        upload_dir = ensure_upload_dir(sub_path)
        file_path = upload_dir / stored_name

        # 3. 写入文件到磁盘
        file_path.write_bytes(file_data)

        # 4. 写入数据库记录
        return await cls._create_attachment(
            db=db,
            user_id=user_id,
            owner_type=owner_type,
            owner_id=owner_id,
            original_name=original_name,
            stored_name=stored_name,
            file_path=f"{sub_path}/{stored_name}",
            file_size=file_size,
            mime_type=mime_type,
            file_type="video",
        )

    # ==================== 流式上传 API ====================

    @classmethod
    async def upload_image_stream(
        cls,
        db: AsyncSession,
        user_id: int,
        file: UploadFile,
        owner_type: str = "user",
        owner_id: int | None = None,
    ) -> Attachment:
        """流式上传图片（Controller 直接传 UploadFile）

        Args:
            db: 数据库会话
            user_id: 上传用户 ID
            file: FastAPI UploadFile 对象
        """
        ext = Path(file.filename or "image").suffix.lower()
        validate_image(ext, 0)

        sub_path, stored_name, file_size = await write_stream(
            file, IMAGE_MAX_SIZE, "images"
        )

        return await cls._create_attachment(
            db=db,
            user_id=user_id,
            owner_type=owner_type,
            owner_id=owner_id,
            original_name=file.filename or "unknown",
            stored_name=stored_name,
            file_path=f"{sub_path}/{stored_name}",
            file_size=file_size,
            mime_type=file.content_type or "application/octet-stream",
            file_type="image",
        )

    @classmethod
    async def upload_video_stream(
        cls,
        db: AsyncSession,
        user_id: int,
        file: UploadFile,
        owner_type: str = "user",
        owner_id: int | None = None,
    ) -> Attachment:
        """流式上传视频（Controller 直接传 UploadFile）

        Args:
            db: 数据库会话
            user_id: 上传用户 ID
            file: FastAPI UploadFile 对象
        """
        ext = Path(file.filename or "video").suffix.lower()
        validate_video(ext, 0)

        sub_path, stored_name, file_size = await write_stream(
            file, VIDEO_MAX_SIZE, "videos"
        )

        return await cls._create_attachment(
            db=db,
            user_id=user_id,
            owner_type=owner_type,
            owner_id=owner_id,
            original_name=file.filename or "unknown",
            stored_name=stored_name,
            file_path=f"{sub_path}/{stored_name}",
            file_size=file_size,
            mime_type=file.content_type or "application/octet-stream",
            file_type="video",
        )

    # ==================== 文件已落盘后创建记录 ====================

    @classmethod
    async def upload_image_from_path(
        cls,
        db: AsyncSession,
        user_id: int,
        original_name: str,
        mime_type: str,
        stored_path: str,
        file_size: int,
        owner_type: str = "user",
        owner_id: int | None = None,
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
        validate_image(ext, file_size)
        return await cls._create_attachment(
            db=db,
            user_id=user_id,
            owner_type=owner_type,
            owner_id=owner_id,
            original_name=original_name,
            stored_name=Path(stored_path).name,
            file_path=stored_path,
            file_size=file_size,
            mime_type=mime_type,
            file_type="image",
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
        owner_type: str = "user",
        owner_id: int | None = None,
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
        validate_video(ext, file_size)
        return await cls._create_attachment(
            db=db,
            user_id=user_id,
            owner_type=owner_type,
            owner_id=owner_id,
            original_name=original_name,
            stored_name=Path(stored_path).name,
            file_path=stored_path,
            file_size=file_size,
            mime_type=mime_type,
            file_type="video",
        )

    # ==================== 数据库操作 ====================

    @classmethod
    async def _create_attachment(
        cls,
        db: AsyncSession,
        user_id: int,
        owner_type: str,
        owner_id: int | None,
        original_name: str,
        stored_name: str,
        file_path: str,
        file_size: int,
        mime_type: str,
        file_type: str,
    ) -> Attachment:
        """创建附件数据库记录"""
        resolved_owner_id = user_id if owner_id is None else owner_id
        attachment = Attachment(
            user_id=user_id,
            owner_type=owner_type,
            owner_id=resolved_owner_id,
            original_name=original_name,
            stored_name=stored_name,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            file_type=file_type,
        )
        db.add(attachment)
        await db.commit()
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
            page_params: 分页参数（page + page_size/size）

        Returns:
            {"items": [...], "total": int, "page": int, "size": int, "total_page": int}
        """
        query = select(Attachment)
        count_query = select(func.count(Attachment.id))

        if user_id is not None:
            query = query.where(Attachment.user_id == user_id)
            count_query = count_query.where(Attachment.user_id == user_id)

        query = query.order_by(Attachment.created_at.desc())

        return await paginate(db, query, page_params, count_query)

    # ==================== URL 生成 ====================

    @staticmethod
    def get_file_url(file_path: str, base_url: str = "") -> str:
        """根据文件相对路径生成完整访问 URL

        Args:
            file_path: 文件相对路径
            base_url: 当前请求的基础 URL（例如 http://localhost:8000/），
                      不传则返回相对路径
        """
        # 统一为正斜杠，兼容 Windows 环境 Path 可能产生的反斜杠
        normalized_path = file_path.replace("\\", "/")
        if base_url:
            base_url = base_url.rstrip("/")
            return f"{base_url}/uploads/{normalized_path}"
        return f"/uploads/{normalized_path}"
