"""
============================================
FastAPI AI Service - 应用入口
============================================
职责：
    - 创建 FastAPI 应用实例
    - 注册 CORS 中间件
    - 注册全局异常处理器
    - 注册所有路由
    - 注册应用生命周期事件

启动方式：
    # 方式一：CLI 启动（推荐开发用）
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

    # 方式二：直接运行（端口从 .env / 默认配置读取）
    python app/main.py
"""

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.common.exception import (
    AppException,
    app_exception_handler,
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.config import settings
from app.core.logging import setup_logging
from app.middleware.request_log import RequestLogMiddleware

setup_logging()
from app.database import engine, init_db  # noqa: E402

# 导入 ORM 模型确保它们注册到 Base.metadata（用于自动建表）
from app.models import (  # noqa: E402
    AiChatLog,  # noqa: F401
    User,  # noqa: F401
    UserToken,  # noqa: F401
    VerificationCode,  # noqa: F401
)
from app.routes import api_router  # noqa: E402

# ==================== 创建应用实例 ====================

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="企业级 FastAPI AI 接口服务（三层架构）",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ==================== CORS 跨域配置 ====================

app.add_middleware(RequestLogMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境请替换为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 注册全局异常处理器 ====================

app.add_exception_handler(AppException, app_exception_handler)  # 自定义业务异常
app.add_exception_handler(HTTPException, http_exception_handler)  # FastAPI HTTP 异常
app.add_exception_handler(RequestValidationError, validation_exception_handler)  # 参数校验异常
app.add_exception_handler(Exception, general_exception_handler)  # 兜底异常

# ==================== 注册路由 ====================

app.include_router(api_router)


# ==================== 生命周期事件 ====================


@app.on_event("startup")
async def startup():
    """应用启动时执行"""
    if settings.AUTO_CREATE_TABLES:
        await init_db()
        print("  ✅ 数据库表初始化完成")
    else:
        print("  数据库自动建表已关闭，请使用 Alembic 管理表结构")
    print(f"  {settings.PROJECT_NAME} v{settings.VERSION} 启动成功")
    print(f"  Swagger 文档: http://localhost:{settings.PORT}/docs")
    print(f"  ReDoc 文档:   http://localhost:{settings.PORT}/redoc")


@app.on_event("shutdown")
async def shutdown():
    """应用关闭时执行"""
    await engine.dispose()
    print("  服务正在关闭... 数据库连接已释放")


# ==================== 根路由 ====================


@app.get("/", tags=["基础"])
async def root():
    """根路径，重定向到文档"""
    return {"message": f"欢迎使用 {settings.PROJECT_NAME}", "docs": "/docs"}


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
