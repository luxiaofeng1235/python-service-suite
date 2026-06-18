"""
============================================
FastAPI AI Service - 应用入口
============================================
组装各模块，保持简洁。具体实现在 app/setup/ 各子模块中。

启动方式：
    # 方式一：CLI 启动（推荐开发用）
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

    # 方式二：直接运行（端口从 .env / 默认配置读取）
    python app/main.py
"""

from fastapi import FastAPI

from app.core.config import settings
from app.pkg.logging import setup_logging
from app.setup import (
    register_middleware,
    register_exception_handlers,
    register_routes,
    register_root_route,
    register_static_files,
    register_docs,
    lifespan,
)

# 日志必须在其他任何操作之前初始化
setup_logging()

# ==================== 导入 ORM 模型 ====================
# 确保模型注册到 Base.metadata，用于自动建表
from app.models import (  # noqa: E402
    AiChatLog,  # noqa: F401
    Attachment,  # noqa: F401
    User,  # noqa: F401
    UserToken,  # noqa: F401
    VerificationCode,  # noqa: F401
    # 后台管理
    AdminToken,  # noqa: F401
    AuthAdmin,  # noqa: F401
    CmsArticle,  # noqa: F401
    CmsTag,  # noqa: F401
    # RBAC 权限
    CasbinRule,  # noqa: F401
    Permission,  # noqa: F401
    Role,  # noqa: F401
    # 其他
    LotteryConfig,  # noqa: F401
)


# ==================== 工厂函数 ====================


def create_app() -> FastAPI:
    """创建并组装 FastAPI 应用实例"""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="企业级 FastAPI AI 接口服务（三层架构）",
        docs_url="/docs",
        redoc_url=None,  # 使用下方自定义路由（固定 ReDoc CDN 版本）
        openapi_url="/openapi.json",
        lifespan=lifespan,  # 使用现代 lifespan 模式替代弃用的 on_event
    )

    register_middleware(app)            # CORS + 请求日志
    register_exception_handlers(app)    # 全局异常处理器
    register_routes(app)                # 业务路由
    register_static_files(app)          # 上传文件静态目录
    register_docs(app)                  # 自定义 ReDoc 文档
    register_root_route(app)            # 根路径

    return app


app = create_app()


# ==================== 直接运行入口 ====================


if __name__ == "__main__":
    """直接运行 python app/main.py 时使用配置中的 HOST 和 PORT"""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )
