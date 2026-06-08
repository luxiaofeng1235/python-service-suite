"""
============================================
配置管理模块 — 项目所有配置统一入口
============================================
敏感信息（密钥、数据库连接串等）统一走 .env，不清真明文到代码中。
所有配置默认值维护在 config/ 目录下（目前：upload / smtp），
Settings 汇聚后支持 .env 环境变量覆盖。
使用方式：
    from app.core.config import settings
    settings.DATABASE_URL
"""

from pydantic_settings import BaseSettings

from config import (
    UPLOAD_DIR,
    FILE_IMAGE,
    FILE_VIDEO,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_SENDER,
    SMTP_SENDER_NAME,
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
    RESET_PASSWORD_BASE_URL,
)


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

    # ==================== 数据库 ====================
    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"
    """数据库连接字符串（通过 .env 配置生产库）"""
    AUTO_CREATE_TABLES: bool = False
    """是否启动时自动 create_all"""

    # ==================== Redis ====================
    REDIS_URL: str | None = None
    """Redis 连接字符串，按需启用"""

    # ==================== 项目信息 ====================
    PROJECT_NAME: str = "FastAPI AI Service"
    VERSION: str = "1.0.0"
    DEBUG: bool = True

    # ==================== 日志 ====================
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "./logs"
    SLOW_REQUEST_MS: int = 1000

    # ==================== 文件上传 ====================
    UPLOAD_DIR: str = UPLOAD_DIR
    """文件上传根目录"""

    FILE_IMAGE_EXTENSIONS: list[str] = FILE_IMAGE["extensions"]
    """允许上传的图片格式"""
    FILE_IMAGE_MAX_SIZE: int = FILE_IMAGE["max_size"]
    """图片最大允许大小（字节）"""

    FILE_VIDEO_EXTENSIONS: list[str] = FILE_VIDEO["extensions"]
    """允许上传的视频格式"""
    FILE_VIDEO_MAX_SIZE: int = FILE_VIDEO["max_size"]
    """视频最大允许大小（字节）"""

    # ==================== 邮件（SMTP）配置 ====================
    SMTP_HOST: str = SMTP_HOST
    SMTP_PORT: int = SMTP_PORT
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_SENDER: str | None = SMTP_SENDER
    SMTP_SENDER_NAME: str | None = SMTP_SENDER_NAME
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
    RESET_PASSWORD_BASE_URL: str = RESET_PASSWORD_BASE_URL

    # ==================== 第三方 API 密钥 ====================
    QWEN_API_KEY: str = ""
    QWEN_CHAT_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    QWEN_MODEL: str = "qwen-max"

    # ==================== 鉴权白名单 ====================
    AUTH_WHITE_LIST: str = (
        "/,/docs,/redoc,/openapi.json,/favicon.ico,"
        "/api/health,/api/user/login,/api/user/register,"
        "/api/user/forgot-password,/api/user/reset-password,"
        "/api/file/upload/image,/api/file/upload/video"
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
