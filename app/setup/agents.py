"""
============================================
商品智能体生命周期 - 共享索引初始化与资源回收
============================================
每个应用进程复用一个商品服务及本地向量库，后台初始化不会阻塞其他业务启动。
关闭时先取消初始化任务，再等待向量线程完成并释放资源。
"""

import asyncio
from datetime import datetime, timedelta

from fastapi import FastAPI

from app.core.config import settings
from app.pkg.logging import app_logger
from app.services.agent.goods_service import GoodsService


async def start_goods_agent(app: FastAPI) -> None:
    """注册共享服务；首次搜索可等待索引，超出工具预算时提示重试。"""
    app.state.goods_service = None
    app.state.goods_index_task = None
    app.state.goods_sync_task = None
    if not settings.GOODS_AGENT_ENABLED:
        return
    service = GoodsService()
    app.state.goods_service = service

    async def initialize() -> None:
        """记录安全的初始化错误，避免连接信息或密钥进入启动日志。"""
        try:
            await service.vector_service.ensure_initialized(service.load_index_batch)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            app_logger.warning(
                "商品索引初始化未完成，异常类型={}；请检查商品表、模型权限和索引目录",
                type(exc).__name__,
            )

    async def periodic_sync() -> None:
        """定期增量同步变更的商品到索引。"""
        # 首次同步从 1 小时前开始，避免遗漏
        last_sync_time = datetime.now() - timedelta(hours=1)
        sync_interval = 300  # 5 分钟同步一次
        
        while True:
            try:
                await asyncio.sleep(sync_interval)
                synced_count = await service.sync_changed_products(last_sync_time)
                if synced_count > 0:
                    app_logger.info("定期同步完成，同步了 {} 个商品", synced_count)
                last_sync_time = datetime.now()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                app_logger.warning(
                    "定期同步失败，异常类型={}，将在下次重试",
                    type(exc).__name__,
                )

    app.state.goods_index_task = asyncio.create_task(initialize(), name="goods-index-initialize")
    app.state.goods_sync_task = asyncio.create_task(periodic_sync(), name="goods-sync-periodic")


async def stop_goods_agent(app: FastAPI) -> None:
    """按依赖顺序关闭初始化任务和向量库，再由应用关闭数据库连接池。"""
    index_task = getattr(app.state, "goods_index_task", None)
    sync_task = getattr(app.state, "goods_sync_task", None)
    service = getattr(app.state, "goods_service", None)
    try:
        try:
            if index_task is not None:
                index_task.cancel()
            if sync_task is not None:
                sync_task.cancel()
            if index_task is not None or sync_task is not None:
                await asyncio.gather(index_task, sync_task, return_exceptions=True)
        finally:
            if service is not None:
                await service.vector_service.aclose()
    finally:
        app.state.goods_service = None
        app.state.goods_index_task = None
        app.state.goods_sync_task = None
