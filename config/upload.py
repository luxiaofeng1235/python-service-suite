"""
============================================
上传配置 — 文件上传相关参数
============================================
"""

# 文件上传限制（图片）
FILE_IMAGE = {
    "extensions": [
        "jpg", "png", "gif", "jpeg", "webp", "bmp", "svg",
    ],
    "max_size": 10 * 1024 * 1024,  # 10 MB
    "dir": "images",
    "description": "允许上传的图片格式与大小限制",
}

# 文件上传限制（视频）
FILE_VIDEO = {
    "extensions": [
        "wmv", "avi", "mpg", "mpeg", "3gp", "mov",
        "mp4", "flv", "f4v", "rmvb", "mkv", "mp3", "wav",
    ],
    "max_size": 200 * 1024 * 1024,  # 200 MB
    "dir": "videos",
    "description": "允许上传的视频格式与大小限制",
}

# 上传根目录
UPLOAD_DIR = "./uploads"
