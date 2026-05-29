"""
============================================
配置管理模块 — 项目所有配置统一入口
============================================
所有配置集中在此管理，敏感信息从 .env 文件读取。
使用方式：
    from app.core.config import settings
    settings.DATABASE_URL
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置类 — 唯一配置入口"""

    # ==================== JWT / 安全 ====================
    SECRET_KEY: str = "your-secret-key-change-in-production"
    """JWT 签名密钥（生产环境务必修改）"""
    ALGORITHM: str = "HS256"
    """JWT 加密算法"""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    """Token 过期时间（分钟），默认 24 小时"""

    # ==================== 服务 ====================
    HOST: str = "0.0.0.0"
    """服务监听地址"""
    PORT: int = 8000
    """服务监听端口"""

    # ==================== 数据库 ====================
    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"
    """数据库连接字符串，默认使用 SQLite"""
    # MySQL 示例：mysql+aiomysql://root:password@localhost:3306/fastapi_ai
    AUTO_CREATE_TABLES: bool = False
    """是否启动时自动 create_all；推荐开发初始化后关闭，表结构变更使用 Alembic"""

    # ==================== Redis ====================
    REDIS_URL: str | None = None
    """Redis 连接字符串，按需启用"""

    # ==================== 项目信息 ====================
    PROJECT_NAME: str = "FastAPI AI Service"
    """项目名称"""
    VERSION: str = "1.0.0"
    """项目版本号"""
    DEBUG: bool = True
    """调试模式开关"""

    # ==================== 日志 ====================
    LOG_LEVEL: str = "INFO"
    """日志级别"""
    LOG_DIR: str = "./logs"
    """日志目录"""
    SLOW_REQUEST_MS: int = 1000
    """慢请求阈值，单位毫秒"""

    # ==================== 上传 ====================
    UPLOAD_DIR: str = "./uploads"
    """文件上传目录"""

    # ==================== 邮件（SMTP）配置 ====================
    SMTP_HOST: str = "smtp.qq.com"
    """SMTP 服务器地址"""
    SMTP_PORT: int = 465
    """SMTP 端口（465=SSL / 587=STARTTLS）"""
    SMTP_USER: str = ""
    """SMTP 登录用户名（邮箱地址）"""
    SMTP_PASSWORD: str = ""
    """SMTP 授权码（非邮箱密码）"""
    SMTP_SENDER: str | None = None
    """发件人地址（默认同 SMTP_USER）"""
    SMTP_SENDER_NAME: str | None = None
    """发件人显示名称（默认同 PROJECT_NAME）"""
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30
    """密码重置验证码过期时间（分钟）"""
    RESET_PASSWORD_BASE_URL: str = "http://localhost:3000/reset-password"
    """前端重置密码页面的 URL（验证码模式下前端自行处理）"""

    # ==================== 第三方 API 密钥 ====================
    # AI 模型 API Key 等敏感信息在此声明，从 .env 读取
    QWEN_API_KEY: str = ""
    """阿里云百炼 / 千问兼容模式 API Key"""
    QWEN_CHAT_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    """千问 OpenAI 兼容模式聊天接口"""
    QWEN_MODEL: str = "qwen-max"
    """默认千问聊天模型"""

    # ==================== 鉴权白名单 ====================
    AUTH_WHITE_LIST: str = (
        "/,/docs,/redoc,/openapi.json,/favicon.ico,"
        "/api/health,/api/user/login,/api/user/register,"
        "/api/user/forgot-password,/api/user/reset-password,"
        "/api/ai/chat,/api/ai/chat/send_stream_sse"
    )
    """免登录路径前缀，英文逗号分隔"""

    model_config = {
        "env_file": ".env",  # 从 .env 文件读取
        "env_file_encoding": "utf-8",  # 编码
        "case_sensitive": True,  # 大小写敏感
    }


# ==================== 全局单例 ====================
settings = Settings()
"""全局唯一配置实例，其他地方统一导入此实例"""
