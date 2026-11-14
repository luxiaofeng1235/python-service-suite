"""
============================================
公共附件服务 - 本地与 OSS 上传
============================================
供前台与后台复用附件上传、归属记录、文件查询和访问地址生成。
文件 I/O 和格式、大小校验委托给 storage 模块。
"""

from pathlib import Path
from urllib.parse import urlsplit

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.common.pagination import PageParams, paginate
from app.models.attachment import Attachment
from app.pkg.logging import app_logger
from app.storage.local import ensure_upload_dir, generate_stored_name, get_upload_size, write_stream
from app.storage.oss import OSSStorage
from app.storage.validation import (
    IMAGE_MAX_SIZE,
    VIDEO_MAX_SIZE,
    get_file_type,
    validate_image,
    validate_video,
)
from app.utils.time_ import TimeUtil


class FileService:
    """文件上传业务逻辑"""

    LEGACY_USER_ID = 0
    OWNER_USER = "user"
    OWNER_ADMIN = "admin"
    OWNER_SYSTEM = "system"

    @staticmethod
    def _legacy_user_id(owner_type: str, owner_id: int) -> int:
        """Map new ownership fields to the legacy user_id column."""
        return owner_id if owner_type == FileService.OWNER_USER else FileService.LEGACY_USER_ID

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
        date_str = TimeUtil.get_date().strftime("%Y/%m")
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
        date_str = TimeUtil.get_date().strftime("%Y/%m")
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
        return await cls.upload_image_stream_for_owner(
            db=db,
            owner_type=owner_type,
            owner_id=user_id if owner_id is None else owner_id,
            file=file,
        )

    @classmethod
    async def upload_image_stream_for_owner(
        cls,
        db: AsyncSession,
        owner_type: str,
        owner_id: int,
        file: UploadFile,
    ) -> Attachment:
        """按统一归属字段流式上传图片。"""
        ext = Path(file.filename or "image").suffix.lower()
        validate_image(ext, 0)

        sub_path, stored_name, file_size = await write_stream(file, IMAGE_MAX_SIZE, "images")

        return await cls._create_attachment(
            db=db,
            user_id=cls._legacy_user_id(owner_type, owner_id),
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
        return await cls.upload_video_stream_for_owner(
            db=db,
            owner_type=owner_type,
            owner_id=user_id if owner_id is None else owner_id,
            file=file,
        )

    @classmethod
    async def upload_video_stream_for_owner(
        cls,
        db: AsyncSession,
        owner_type: str,
        owner_id: int,
        file: UploadFile,
    ) -> Attachment:
        """按统一归属字段流式上传视频。"""
        ext = Path(file.filename or "video").suffix.lower()
        validate_video(ext, 0)

        sub_path, stored_name, file_size = await write_stream(file, VIDEO_MAX_SIZE, "videos")

        return await cls._create_attachment(
            db=db,
            user_id=cls._legacy_user_id(owner_type, owner_id),
            owner_type=owner_type,
            owner_id=owner_id,
            original_name=file.filename or "unknown",
            stored_name=stored_name,
            file_path=f"{sub_path}/{stored_name}",
            file_size=file_size,
            mime_type=file.content_type or "application/octet-stream",
            file_type="video",
        )

    # ==================== OSS 上传 ====================

    @classmethod
    async def upload_oss(
        cls,
        db: AsyncSession,
        *,
        owner_type: str,
        owner_id: int,
        upload_type: str = "local",
        file: UploadFile | None = None,
        url: str | None = None,
    ) -> Attachment:
        """统一校验上传参数，并按类型分发本地文件或远程 URL 的 OSS 上传。"""
        if upload_type not in ("local", "url"):
            raise AppException(msg="upload_type 必须为 local 或 url")

        if upload_type == "local":
            if file is None:
                raise AppException(msg="upload_type=local 时必须提供 file 参数")
            if url:
                raise AppException(msg="upload_type=local 时不应提供 url 参数")
            return await cls.upload_oss_for_owner(
                db,
                owner_type=owner_type,
                owner_id=owner_id,
                file=file,
            )

        if not url:
            raise AppException(msg="upload_type=url 时必须提供 url 参数")
        if file is not None:
            raise AppException(msg="upload_type=url 时不应提供 file 参数")
        return await cls.upload_oss_from_url(
            db,
            owner_type=owner_type,
            owner_id=owner_id,
            url=url,
        )

    @classmethod
    async def upload_oss_for_owner(
        cls,
        db: AsyncSession,
        owner_type: str,
        owner_id: int,
        file: UploadFile,
    ) -> Attachment:
        """Validate an upload, store it in OSS, and persist its ownership and metadata."""
        original_name = file.filename or "unknown"
        mime_type = file.content_type or "application/octet-stream"
        if len(original_name) > 255:
            raise AppException(msg="文件名过长，最多支持 255 个字符")
        if len(mime_type) > 100:
            raise AppException(msg="文件 MIME 类型过长")

        ext = Path(original_name).suffix.lower()
        file_type = get_file_type(ext)
        if file_type not in {"image", "video"}:
            raise AppException(msg="不支持的附件格式，仅支持配置中允许的图片和视频")
        validator = validate_image if file_type == "image" else validate_video
        validator(ext, 0)
        file_size = await get_upload_size(file)
        validator(ext, file_size)
        if file_size == 0:
            raise AppException(msg="上传文件不能为空")

        OSSStorage.validate_config()
        stored_name, _, _ = generate_stored_name(original_name)
        directory = "images" if file_type == "image" else "videos"
        object_key = f"uploads/{directory}/{TimeUtil.get_date():%Y/%m}/{stored_name}"
        if len(OSSStorage.get_url(object_key)) > 500:
            raise AppException(msg="OSS 文件访问地址过长，请检查域名配置")

        url = await OSSStorage.upload_stream(file.file, object_key, content_type=mime_type)
        try:
            return await cls._create_attachment(
                db=db,
                user_id=cls._legacy_user_id(owner_type, owner_id),
                owner_type=owner_type,
                owner_id=owner_id,
                original_name=original_name,
                stored_name=stored_name,
                file_path=url,
                file_size=file_size,
                mime_type=mime_type,
                file_type=file_type,
            )
        except Exception:
            await db.rollback()
            # 入库失败时清理本次上传，避免留下没有附件记录的 OSS 文件。
            try:
                await OSSStorage.delete_object(object_key)
            except AppException:
                app_logger.error("附件保存失败，OSS 文件清理失败，object_key={}", object_key)
            raise

    # ==================== URL 上传到 OSS ====================

    @classmethod
    async def upload_oss_from_url(
        cls,
        db: AsyncSession,
        owner_type: str,
        owner_id: int,
        url: str,
    ) -> Attachment:
        """从远程 URL 下载文件到 OSS，支持自动类型识别和校验。

        Args:
            db: 数据库会话
            owner_type: 所有者类型（user/admin/system）
            owner_id: 所有者 ID
            url: 远程文件 URL（http:// 或 https://）

        Returns:
            创建的 Attachment 记录
        """
        # 1. URL 格式校验
        if not url or len(url) > 2048:
            raise AppException(msg="URL 格式错误或过长，最多 2048 字符")
        if not url.startswith(("http://", "https://")):
            raise AppException(msg="URL 必须以 http:// 或 https:// 开头")

        # 2. 从 URL 路径推断文件名和类型
        path_part = urlsplit(url).path.lower()
        original_name = Path(path_part).name or "download"
        ext = Path(original_name).suffix.lower()

        # 若无后缀，尝试添加默认后缀
        if not ext:
            ext = ".jpg"
            original_name = f"{original_name}{ext}"

        # 3. 校验文件类型
        file_type = get_file_type(ext)
        if file_type not in {"image", "video"}:
            raise AppException(msg="不支持的附件格式，仅支持配置中允许的图片和视频")

        # 4. 预校验格式（无 file_size）
        validator = validate_image if file_type == "image" else validate_video
        validator(ext, 0)

        # 5. OSS 配置校验
        OSSStorage.validate_config()

        # 6. 生成存储路径
        stored_name, _, _ = generate_stored_name(original_name)
        directory = "images" if file_type == "image" else "videos"
        object_key = f"uploads/{directory}/{TimeUtil.get_date():%Y/%m}/{stored_name}"

        # 7. 预校验 OSS URL 长度
        if len(OSSStorage.get_url(object_key)) > 500:
            raise AppException(msg="OSS 文件访问地址过长，请检查域名配置")

        # 8. 从 URL 下载并上传到 OSS（会校验大小）
        max_size = IMAGE_MAX_SIZE if file_type == "image" else VIDEO_MAX_SIZE
        try:
            oss_url = await OSSStorage.upload_url(
                url,
                object_key,
                max_size=max_size,
            )
        except AppException as exc:
            # 保留原始错误信息（已经过滤认证信息）
            raise exc

        # 9. 创建数据库记录
        try:
            return await cls._create_attachment(
                db=db,
                user_id=cls._legacy_user_id(owner_type, owner_id),
                owner_type=owner_type,
                owner_id=owner_id,
                original_name=original_name,
                stored_name=stored_name,
                file_path=oss_url,  # OSS 完整 URL
                file_size=0,  # URL 上传时无法获取准确大小，后续可从 OSS 元数据更新
                mime_type="application/octet-stream",
                file_type=file_type,
            )
        except Exception:
            await db.rollback()
            # 入库失败时清理 OSS 文件
            try:
                await OSSStorage.delete_object(object_key)
            except AppException:
                app_logger.error("URL 文件保存失败，OSS 文件清理失败，object_key={}", object_key)
            raise

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
        # 提交前完成刷新，避免提交成功后的刷新异常触发 OSS 文件清理。
        await db.flush()
        await db.refresh(attachment)
        await db.commit()
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
                      不传则优先使用 settings.FILE_BASE_URL，再退化为相对路径
        """
        from app.core.config import settings

        # 统一为正斜杠，兼容 Windows 环境 Path 可能产生的反斜杠
        normalized_path = file_path.replace("\\", "/")
        if normalized_path.startswith(("https://", "http://")):
            return normalized_path
        if not base_url:
            base_url = settings.FILE_BASE_URL
        if base_url:
            base_url = base_url.rstrip("/")
            return f"{base_url}/uploads/{normalized_path}"
        return f"/uploads/{normalized_path}"
