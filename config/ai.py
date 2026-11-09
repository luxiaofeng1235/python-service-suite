"""
============================================
AI Configuration - endpoints, models and video processing
============================================
Maintain AI options here; backend API credentials are read from .env.
"""

# 千问地址和默认模型；QWEN_API_KEY 由后端 .env 提供。
QWEN_CHAT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
QWEN_MODEL = "qwen-max"
QWEN_IMAGE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
QWEN_VIDEO_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
QWEN_TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks"

# 图片和视频任务共用的 HTTP 超时（秒），生成进度由客户端轮询。
QWEN_REQUEST_TIMEOUT = 60.0
QWEN_CONNECT_TIMEOUT = 30.0

# 视频下载后使用 FFmpeg 加 PNG 水印，再上传 OSS。
AI_VIDEO_WATERMARK_PATH = "./public/watermark.png"
AI_VIDEO_BASE_URL = "https://static-nine-world.oss-cn-shanghai.aliyuncs.com"
FFMPEG_BIN = "ffmpeg"
AI_VIDEO_FFMPEG_TIMEOUT = 600
