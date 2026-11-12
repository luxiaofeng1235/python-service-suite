"""
============================================
应用生命周期事件注册
============================================
使用现代 FastAPI lifespan 模式替代弃用的 on_event。
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.database import engine, init_db
from app.pkg.logging import app_logger
from app.pkg.redis_client import redis_client
from app.setup.agents import start_goods_agent, stop_goods_agent


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期 — startup / shutdown"""
    # ==================== startup ====================
    if settings.AUTO_CREATE_TABLES:
        await init_db()
        print("  ✅ 数据库表初始化完成")
    else:
        print("  数据库自动建表已关闭，请使用 Alembic 管理表结构")

    # Redis 初始化（若配置了 REDIS_URL 则自动连接）
    if settings.REDIS_URL:
        try:
            await redis_client.init()
            await redis_client.client.ping()
            print("  ✅ Redis 连接成功")
        except Exception as e:
            print(f"  ⚠️  Redis 连接失败: {e}（项目仍可运行，缓存功能不可用）")
    else:
        print("  ℹ️  未配置 REDIS_URL，跳过 Redis 连接（如需缓存请设置 REDIS_URL）")

    await start_goods_agent(app)

    print(f"  {settings.PROJECT_NAME} v{settings.VERSION} 启动成功")
    print(f"  Swagger 文档: http://localhost:{settings.PORT}/docs")
    print(f"  ReDoc 文档:   http://localhost:{settings.PORT}/redoc")

    try:
        yield
    except asyncio.CancelledError:
        # Ctrl+C 关闭时 asyncio 会抛 CancelledError，静默处理即可
        pass
    finally:
        # ==================== shutdown ====================
        # 单个资源关闭失败不影响后续连接池和 Redis 的回收。
        for name, close in (
            ("商品 Agent", lambda: stop_goods_agent(app)),
            ("数据库", engine.dispose),
            ("Redis", redis_client.close),
        ):
            try:
                await close()
            except asyncio.CancelledError:
                continue
            except Exception as exc:
                app_logger.warning("{} 资源关闭失败，异常类型={}", name, type(exc).__name__)
        app_logger.info("服务关闭资源回收已完成")
