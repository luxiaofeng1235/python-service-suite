"""
============================================
文件校验规则
============================================
职责：文件类型识别、格式校验、大小校验。
不包含任何 I/O 操作和业务编排。
"""

from app.common.exception import AppException
from app.core.config import settings


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


# ==================== 文件类型判断 ====================

def get_file_type(ext: str) -> str:
    """根据扩展名判断文件分类"""
    ext = ext.lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return "other"


# ==================== 格式与大校校验 ====================

def validate_image(ext: str, file_size: int) -> None:
    """校验图片格式与大小"""
    if ext not in IMAGE_EXTENSIONS:
        raise AppException(msg=f"不支持的图片格式：{ext}，仅支持 {', '.join(sorted(IMAGE_EXTENSIONS))}")
    if file_size > IMAGE_MAX_SIZE:
        raise AppException(msg=f"图片大小超过限制（最大 {IMAGE_MAX_SIZE // 1024 // 1024} MB）")


def validate_video(ext: str, file_size: int) -> None:
    """校验视频格式与大小"""
    if ext not in VIDEO_EXTENSIONS:
        raise AppException(msg=f"不支持的视频格式：{ext}，仅支持 {', '.join(sorted(VIDEO_EXTENSIONS))}")
    if file_size > VIDEO_MAX_SIZE:
        raise AppException(msg=f"视频大小超过限制（最大 {VIDEO_MAX_SIZE // 1024 // 1024} MB）")
