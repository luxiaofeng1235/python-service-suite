"""
============================================
配置管理模块 — 项目所有配置统一入口
============================================
敏感信息（密钥、数据库连接串等）统一由 .env 提供。
按模块读取 config/ 中的业务默认值，Settings 负责类型校验与 .env 覆盖。
使用方式：
    from app.core.config import settings
    settings.DATABASE_URL
"""

from pydantic import Field
from pydantic_settings import BaseSettings

from config import goods, oss, qwenai, smtp, upload


class Settings(BaseSettings):
    """应用配置类 — 唯一配置入口，支持 .env 环境变量覆盖"""

    # ==================== JWT / 安全 ====================
    SECRET_KEY: str = ""
    """JWT 签名密钥（通过 .env 配置）"""
    ALGORITHM: str = "HS256"
    """JWT 加密算法"""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200
    """Token 过期时间（分钟），默认 30 天"""

    # ==================== 服务 ====================
    HOST: str = "0.0.0.0"
    """服务监听地址"""
    PORT: int = 8000
    """服务监听端口"""

    # ==================== WebSocket ====================
    WEBSOCKET_SEND_TIMEOUT: float = Field(10.0, gt=0)
    """单条消息发送及连接关闭的超时时间（秒）"""

    # ==================== 数据库 ====================
    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"
    """数据库连接字符串（通过 .env 配置生产库）"""
    AUTO_CREATE_TABLES: bool = False
    """是否启动时自动 create_all"""

    # ==================== Redis ====================
    REDIS_URL: str | None = None
    """Redis 连接字符串，按需启用"""

    # ==================== 项目信息 ====================
    PROJECT_NAME: str = "OmniCore Platform"
    VERSION: str = "1.0.0"
    DEBUG: bool = True

    # ==================== 日志 ====================
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "./logs"
    SLOW_REQUEST_MS: int = 1000

    # ==================== 文件上传 ====================
    UPLOAD_DIR: str = upload.UPLOAD_DIR
    """文件上传根目录"""

    FILE_IMAGE_EXTENSIONS: list[str] = upload.FILE_IMAGE["extensions"]
    """允许上传的图片格式"""
    FILE_IMAGE_MAX_SIZE: int = upload.FILE_IMAGE["max_size"]
    """图片最大允许大小（字节）"""

    FILE_VIDEO_EXTENSIONS: list[str] = upload.FILE_VIDEO["extensions"]
    """允许上传的视频格式"""
    FILE_VIDEO_MAX_SIZE: int = upload.FILE_VIDEO["max_size"]
    """视频最大允许大小（字节）"""

    FILE_BASE_URL: str = upload.FILE_BASE_URL
    """文件访问基础URL，支持 .env 覆盖，留空可使用相对路径"""

    # ==================== 阿里云 OSS ====================
    OSS_ENABLED: bool = oss.OSS_ENABLED
    """是否将 AI 生成图片和加水印的视频同步到 OSS"""
    OSS_ACCESS_KEY_ID: str = ""
    OSS_ACCESS_KEY_SECRET: str = ""
    OSS_ENDPOINT: str = oss.OSS_ENDPOINT
    OSS_REGION: str = oss.OSS_REGION
    OSS_BUCKET: str = oss.OSS_BUCKET
    OSS_VIEW_DOMAIN: str = oss.OSS_VIEW_DOMAIN
    OSS_ROLEARN: str = ""
    OSS_TOKENEXPIRETIME: int = oss.OSS_TOKENEXPIRETIME
    OSS_POLICYFILE: str = oss.OSS_POLICYFILE

    # ==================== 邮件（SMTP）配置 ====================
    SMTP_HOST: str = smtp.SMTP_HOST
    SMTP_PORT: int = smtp.SMTP_PORT
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_SENDER: str | None = smtp.SMTP_SENDER
    SMTP_SENDER_NAME: str | None = smtp.SMTP_SENDER_NAME
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = smtp.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
    RESET_PASSWORD_BASE_URL: str = smtp.RESET_PASSWORD_BASE_URL

    # ==================== 第三方 API 密钥 ====================
    QWEN_API_KEY: str = ""
    QWEN_CHAT_URL: str = qwenai.QWEN_CHAT_URL
    QWEN_MODEL: str = qwenai.QWEN_MODEL
    QWEN_EMBEDDING_URL: str = qwenai.QWEN_EMBEDDING_URL
    QWEN_EMBEDDING_MODEL: str = qwenai.QWEN_EMBEDDING_MODEL
    QWEN_EMBEDDING_DIMENSIONS: int = Field(qwenai.QWEN_EMBEDDING_DIMENSIONS, ge=64, le=2048)
    QWEN_EMBEDDING_TIMEOUT: float = Field(qwenai.QWEN_EMBEDDING_TIMEOUT, gt=0)
    QWEN_OMNI_MODEL: str = qwenai.QWEN_OMNI_MODEL
    QWEN_OMNI_AUDIO_VOICE: str = qwenai.QWEN_OMNI_AUDIO_VOICE
    QWEN_OMNI_AUDIO_FORMAT: str = qwenai.QWEN_OMNI_AUDIO_FORMAT
    QWEN_TTS_URL: str = qwenai.QWEN_TTS_URL
    QWEN_TTS_MODEL: str = qwenai.QWEN_TTS_MODEL
    QWEN_TTS_VOICE: str = qwenai.QWEN_TTS_VOICE
    QWEN_TTS_LANGUAGE_TYPE: str = qwenai.QWEN_TTS_LANGUAGE_TYPE
    QWEN_IMAGE_URL: str = qwenai.QWEN_IMAGE_URL
    QWEN_IMAGE_MODEL: str = qwenai.QWEN_IMAGE_MODEL
    QWEN_IMAGE_PRO_MODEL: str = qwenai.QWEN_IMAGE_PRO_MODEL
    AI_IMAGE_MAX_SIZE: int = Field(qwenai.AI_IMAGE_MAX_SIZE, gt=0)
    QWEN_TASK_URL: str = qwenai.QWEN_TASK_URL
    QWEN_VIDEO_URL: str = qwenai.QWEN_VIDEO_URL
    QWEN_VIDEO_MODEL: str = qwenai.QWEN_VIDEO_MODEL
    AI_VIDEO_DEFAULT_RESOLUTION: str = qwenai.AI_VIDEO_DEFAULT_RESOLUTION
    AI_VIDEO_DEFAULT_DURATION: int = Field(qwenai.AI_VIDEO_DEFAULT_DURATION, ge=2, le=30)
    AI_VIDEO_DEFAULT_RATIO: str = qwenai.AI_VIDEO_DEFAULT_RATIO
    AI_VIDEO_DEFAULT_AUDIO: bool = qwenai.AI_VIDEO_DEFAULT_AUDIO
    QWEN_REQUEST_TIMEOUT: float = qwenai.QWEN_REQUEST_TIMEOUT
    QWEN_CONNECT_TIMEOUT: float = qwenai.QWEN_CONNECT_TIMEOUT

    # ==================== Agent 底座 ====================
    AGENT_LLM_PROVIDER: str = qwenai.AGENT_LLM_PROVIDER
    AGENT_MODEL: str = qwenai.AGENT_MODEL
    AGENT_ENABLE_SEARCH: bool = qwenai.AGENT_ENABLE_SEARCH
    AGENT_MAX_TOOL_ROUNDS: int = Field(qwenai.AGENT_MAX_TOOL_ROUNDS, ge=0, le=20)
    AGENT_MAX_TOOL_CALLS: int = Field(qwenai.AGENT_MAX_TOOL_CALLS, ge=1, le=10)
    AGENT_MAX_HISTORY_MESSAGES: int = Field(qwenai.AGENT_MAX_HISTORY_MESSAGES, ge=2, le=500)
    AGENT_MAX_HISTORY_CHARS: int = Field(qwenai.AGENT_MAX_HISTORY_CHARS, ge=1000, le=200000)
    AGENT_TOOL_TIMEOUT: float = Field(qwenai.AGENT_TOOL_TIMEOUT, gt=0)
    AGENT_RUN_TIMEOUT: float = Field(qwenai.AGENT_RUN_TIMEOUT, gt=0)
    AGENT_TIMEZONE: str = qwenai.AGENT_TIMEZONE

    # ==================== 商品 Agent ====================
    GOODS_AGENT_ENABLED: bool = goods.GOODS_AGENT_ENABLED
    GOODS_AGENT_MODEL: str = Field(goods.GOODS_AGENT_MODEL, min_length=1)
    GOODS_CHROMA_PATH: str = goods.GOODS_CHROMA_PATH
    GOODS_CHROMA_COLLECTION: str = goods.GOODS_CHROMA_COLLECTION
    GOODS_INDEX_BATCH_SIZE: int = Field(goods.GOODS_INDEX_BATCH_SIZE, ge=1, le=500)
    GOODS_EMBEDDING_BATCH_SIZE: int = Field(goods.GOODS_EMBEDDING_BATCH_SIZE, ge=1, le=10)
    GOODS_INDEX_SCHEMA_VERSION: int = Field(goods.GOODS_INDEX_SCHEMA_VERSION, ge=1)
    GOODS_INDEX_TIMEOUT: float = Field(goods.GOODS_INDEX_TIMEOUT, gt=0)
    GOODS_SEARCH_TOP_K: int = Field(goods.GOODS_SEARCH_TOP_K, ge=1, le=100)
    GOODS_SEARCH_MAX_DISTANCE: float = Field(goods.GOODS_SEARCH_MAX_DISTANCE, ge=0, le=2)
    GOODS_SEARCH_RESULT_LIMIT: int = Field(goods.GOODS_SEARCH_RESULT_LIMIT, ge=1, le=10)

    # ==================== 视频水印 ====================
    AI_VIDEO_WATERMARK_PATH: str = qwenai.AI_VIDEO_WATERMARK_PATH
    AI_VIDEO_BASE_URL: str = qwenai.AI_VIDEO_BASE_URL
    FFMPEG_BIN: str = qwenai.FFMPEG_BIN
    AI_VIDEO_FFMPEG_TIMEOUT: int = qwenai.AI_VIDEO_FFMPEG_TIMEOUT

    # ==================== 鉴权白名单 ====================
    AUTH_WHITE_LIST: str = (
        "/,/docs,/redoc,/openapi.json,/favicon.ico,"
        "/api/health,/api/user/login,/api/user/register,"
        "/api/user/forgot-password,/api/user/reset-password,"
        "/api/file/upload/image,/api/file/upload/video,"
        "/api/file/upload/oss"
    )

    @property
    def white_list(self) -> list[str]:
        """解析 AUTH_WHITE_LIST 字符串为路由白名单列表"""
        return [item.strip() for item in self.AUTH_WHITE_LIST.split(",") if item.strip()]

    # ==================== API 加解密 ====================
    API_ENCRYPT_ENABLED: bool = False
    """是否开启接口请求参数加密签名校验（关闭则明文传输）"""
    API_ENCRYPT_KEY: str = ""
    """接口加密密钥（开启加密时必填）"""

    # ==================== CORS ====================
    CORS_ORIGINS: list[str] = ["*"]
    """允许的跨域来源，生产环境建议设为具体域名，如 ["https://example.com"]"""

    # ==================== 密码重置限速 ====================
    RATE_LIMIT_FORGOT_PASSWORD_MAX: int = 3
    """同一邮箱每段时间内最多请求 forgot-password 次数"""
    RATE_LIMIT_RESET_PASSWORD_MAX: int = 5
    """同一邮箱每段时间内最多请求 reset-password 次数"""
    RATE_LIMIT_WINDOW_SECONDS: int = 300
    """限速时间窗口（秒），默认 5 分钟"""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


# ==================== 全局单例 ====================
settings = Settings()
"""全局唯一配置实例，其他地方统一导入此实例"""
