"""
============================================
AI Configuration - endpoints, models and video processing
============================================
Maintain AI options here; backend API credentials are read from .env.
"""

# 千问地址和默认模型；QWEN_API_KEY 由后端 .env 提供。
QWEN_CHAT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
QWEN_MODEL = "qwen-max"
# 多模态流式对话由后端固定模型、音色和输出格式。
QWEN_OMNI_MODEL = "qwen3-omni-flash"
QWEN_OMNI_AUDIO_VOICE = "Cherry"
QWEN_OMNI_AUDIO_FORMAT = "wav"
# 文本转语音使用普通 HTTP 请求，生成后返回完整音频地址。
QWEN_TTS_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
QWEN_TTS_MODEL = "qwen3-tts-flash"
QWEN_TTS_VOICE = "Cherry"
QWEN_TTS_LANGUAGE_TYPE = "Chinese"
QWEN_IMAGE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
QWEN_VIDEO_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
QWEN_TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks"

# 商品向量化复用千问密钥和公共 HTTP 请求，仅使用独立的 Embedding 地址。
QWEN_EMBEDDING_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
QWEN_EMBEDDING_MODEL = "text-embedding-v4"
QWEN_EMBEDDING_DIMENSIONS = 1024
QWEN_EMBEDDING_TIMEOUT = 20.0

# 图片和视频任务共用的 HTTP 超时（秒），生成进度由客户端轮询。
QWEN_REQUEST_TIMEOUT = 60.0
QWEN_CONNECT_TIMEOUT = 30.0

# Agent 使用独立模型策略，复用已有千问密钥与请求地址。
AGENT_LLM_PROVIDER = "qwen"
AGENT_MODEL = "qwen-plus"
# Agent 是否允许千问使用互联网搜索；密钥和开关均由后端控制。
AGENT_ENABLE_SEARCH = True
AGENT_MAX_TOOL_ROUNDS = 4
AGENT_MAX_TOOL_CALLS = 4
AGENT_MAX_HISTORY_MESSAGES = 60
AGENT_MAX_HISTORY_CHARS = 24000
AGENT_TOOL_TIMEOUT = 30.0
AGENT_RUN_TIMEOUT = 300.0
AGENT_TIMEZONE = "Asia/Shanghai"

# 视频下载后使用 FFmpeg 加 PNG 水印，再上传 OSS。
AI_VIDEO_WATERMARK_PATH = "./public/watermark.png"
AI_VIDEO_BASE_URL = "https://static-nine-world.oss-cn-shanghai.aliyuncs.com"
FFMPEG_BIN = "ffmpeg"
AI_VIDEO_FFMPEG_TIMEOUT = 600
