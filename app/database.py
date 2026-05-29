"""
============================================
数据库引擎与会话管理模块
============================================
使用 SQLAlchemy 2.0 async 模式连接 MySQL。
所有依赖此 Session 的地方统一导入 async_session 工厂。
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# ==================== 引擎 & Session 工厂 ====================

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # 关闭 SQL 日志（太吵）
    pool_size=10,  # 连接池大小
    max_overflow=20,  # 最大溢出连接数
    pool_recycle=1800,  # 连接回收时间（秒）
    pool_pre_ping=True,  # 取连接前探活，避免 MySQL 断开旧连接
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # 提交后不过期，方便读取
)


# ==================== ORM 基类 ====================


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""

    pass


# ==================== 便捷工具 ====================


async def get_session() -> AsyncSession:
    """FastAPI 依赖注入：获取数据库会话"""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化数据库：创建所有表（生产环境建议用 Alembic 迁移）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
