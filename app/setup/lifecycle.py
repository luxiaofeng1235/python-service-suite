"""
============================================
应用生命周期事件注册
============================================
使用现代 FastAPI lifespan 模式替代弃用的 on_event。
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.core.config import settings
from app.pkg.redis_client import redis_client
from app.database import engine, init_db


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
        try:
            await engine.dispose()
            await redis_client.close()
            print("  服务正在关闭... 数据库连接已释放")
        except asyncio.CancelledError:
            # 事件循环关闭中，资源释放被中断是预期行为
            pass
        except Exception:
            pass
