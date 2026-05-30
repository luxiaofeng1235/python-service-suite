"""
============================================
本地文件 I/O 层
============================================
职责：文件系统操作——建目录、生成存储文件名、流式写入磁盘。
不包含任何校验逻辑和业务编排。
"""

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile

from app.common.exception import AppException
from app.core.config import settings


def ensure_upload_dir(sub_dir: str) -> Path:
    """确保上传子目录存在并返回 Path 对象"""
    upload_path = Path(settings.UPLOAD_DIR) / sub_dir
    upload_path.mkdir(parents=True, exist_ok=True)
    return upload_path


def generate_stored_name(original_name: str) -> tuple[str, str, str]:
    """生成存储文件名

    Returns:
        (stored_name, ext, stored_filename)
    """
    ext = Path(original_name).suffix.lower()
    stored_name = f"{uuid.uuid4().hex}{ext}"
    return stored_name, ext, stored_name


async def write_stream(
    file: UploadFile,
    max_size: int,
    sub_path_prefix: str,
    chunk_size: int = 64 * 1024,
) -> tuple[str, str, int]:
    """流式写入文件到磁盘（图/视频共用）

    Args:
        file: FastAPI UploadFile 对象
        max_size: 最大字节数
        sub_path_prefix: 子目录前缀（"images" 或 "videos"）
        chunk_size: 分块读取大小

    Returns:
        (sub_path, stored_name, file_size)
    """
    # 1. 生成存储路径（按日期分目录，避免单目录文件过多）
    ext = Path(file.filename or "file").suffix.lower()
    date_str = datetime.now().strftime("%Y/%m")
    stored_name = f"{uuid.uuid4().hex}{ext}"
    sub_path = f"{sub_path_prefix}/{date_str}"
    upload_dir = Path(settings.UPLOAD_DIR) / sub_path
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / stored_name

    # 2. 分块读取并写入磁盘，超出限制时回滚（删除已写入文件）
    file_size = 0
    with open(file_path, "wb") as f:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            file_size += len(chunk)
            if file_size > max_size:
                file_path.unlink(missing_ok=True)
                type_label = "图片" if sub_path_prefix == "images" else "视频"
                max_mb = max_size // 1024 // 1024
                raise AppException(
                    msg=f"{type_label}大小超过限制（最大 {max_mb} MB）"
                )
            f.write(chunk)

    return sub_path, stored_name, file_size
