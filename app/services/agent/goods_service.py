"""
============================================
商品智能体服务 - 语义召回与实时商品事实编排
============================================
以短数据库会话查询品牌和商品，复用公共会话、工具调用及流式响应机制。
向量库仅提供候选，售价、库存和上下架状态始终以本轮 MySQL 查询为准。
"""

import json
import re
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.goods import create_goods_agent
from app.agents.llm.base import LLMAdapter
from app.common.exception import AppException
from app.core.config import settings
from app.database import async_session
from app.pkg.logging import app_logger
from app.schemas.agent.chat import AgentChatRequest, AgentStreamEvent
from app.schemas.agent.goods_data import IndexBatch, ProductDTO
from app.services.agent.chat_service import AgentChatService
from app.services.agent.goods_data_service import GoodsDataService
from app.services.agent.goods_vector_service import GoodsVectorService
from app.utils.time_ import TimeUtil

MAX_TOOL_RESULT_BYTES = 55000
MAX_PRODUCT_DESCRIPTION_CHARS = 1000
_BUDGET_PRICE_RANGE_PATTERN = re.compile(
    r"(?:总预算|预算|总共|一共|总价|控制在)[^\d]{0,12}"
    r"\d+(?:\.\d+)?\s*(?:元|块)?\s*(?:-|–|—|~|～|到|至)\s*\d+"
)
_PRICE_FILTER_PATTERN = re.compile(
    r"\d+(?:\.\d+)?\s*(?:元|块)?\s*"
    r"(?:(?:-|–|—|~|～|到|至)\s*\d+|以上|以下|以内|左右)"
)


class GoodsService:
    """绑定商品只读工具，不向模型暴露数据库写入和索引维护能力。"""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        llm: LLMAdapter | None = None,
        vector_service: GoodsVectorService | None = None,
    ):
        self.session_factory = session_factory or async_session
        self.llm = llm
        self.vector_service = vector_service if vector_service is not None else GoodsVectorService()

    @staticmethod
    def _check_enabled() -> None:
        """在创建会话和调用外部服务前确认商品功能已开启。"""
        if not settings.GOODS_AGENT_ENABLED:
            raise AppException(msg="商品 Agent 未启用")

    def _chat_service(self, user_message: str = "") -> AgentChatService:
        """复用公共聊天存储，由后台登录身份校验会话归属。"""
        price_handler = self._guard_price_handler(user_message)
        runner = create_goods_agent(
            self.search_products,
            self.get_product,
            price_handler,
            llm=self.llm,
        )
        return AgentChatService(runner, session_factory=self.session_factory)

    def _guard_price_handler(self, user_message: str):
        """
        总预算没有单品价格条件时，强制去掉价格工具的筛选参数。

        商品价格区间继续用于筛选，总预算只由总结阶段检查超支。
        """
        has_budget = bool(re.search(r"预算|总共不超过|以内搭配|以内组合", user_message))
        price_filter_message = _BUDGET_PRICE_RANGE_PATTERN.sub("", user_message)
        has_price_filter = bool(_PRICE_FILTER_PATTERN.search(price_filter_message))
        should_clear_price_filter = has_budget and not has_price_filter
        original = self.search_products_by_price

        async def guarded(
            min_price=None, max_price=None, brand=None, product_ids=None, **kwargs
        ):
            if should_clear_price_filter:
                if max_price is not None or min_price is not None:
                    app_logger.info("代码 guard：检测到预算约束，强制去掉价格过滤参数")
                min_price = Decimal("0")
                max_price = None
            return await original(
                min_price=min_price, max_price=max_price,
                brand=brand, product_ids=product_ids, **kwargs,
            )

        return guarded

    async def stream_chat(
        self, req: AgentChatRequest, user_id: int
    ) -> AsyncIterator[AgentStreamEvent]:
        """按现有事件协议执行一次商品查询，退出时关闭底层生成器。"""
        self._check_enabled()
        stream = self._chat_service(req.message).stream_chat(req, user_id)
        try:
            async for event in stream:
                yield event
        finally:
            await stream.aclose()

    async def stream_sse(self, req: AgentChatRequest, user_id: int) -> AsyncIterator[str]:
        """输出 SSE 的 JSON 数据载荷，不改变通用事件字段。"""
        stream = self.stream_chat(req, user_id)
        try:
            async for event in stream:
                yield event.model_dump_json(exclude_none=True)
        finally:
            await stream.aclose()

    async def load_index_batch(self, *, after_id: int = 0, limit: int = 100) -> IndexBatch:
        """为向量首次建库提供游标批次，每批读取后立即归还数据库连接。"""
        async with self.session_factory() as db:
            return await GoodsDataService.get_index_batch(db, after_id=after_id, limit=limit)

    async def refresh_index(self, product_ids: list[int]) -> None:
        """内部同步指定商品的索引资料，并移除当前已下架或删除的商品。"""
        self._check_enabled()
        # 数据层统一校验 ID 类型和数量，验证通过后才操作索引。
        async with self.session_factory() as db:
            documents = await GoodsDataService.get_index_documents(db, product_ids)
        if not product_ids:
            return
        await self.vector_service.ensure_initialized(self.load_index_batch)
        current_ids = {document.product_id for document in documents}
        removed_ids = [
            product_id for product_id in dict.fromkeys(product_ids) if product_id not in current_ids
        ]
        await self.vector_service.upsert(documents)
        await self.vector_service.delete(removed_ids)

    async def rebuild_index(self) -> None:
        """内部完整重建索引，失败时由向量服务保留原来的完整代。"""
        self._check_enabled()
        await self.vector_service.rebuild(self.load_index_batch)

    async def sync_changed_products(self, since: datetime | None = None) -> int:
        """
        增量同步变更的商品到索引。

        参数:
            since: 查询此时间之后变更的商品。如果为 None，则从 collection metadata 中读取上次同步时间。

        返回:
            成功同步的商品数量。
        """
        self._check_enabled()
        
        # 确保索引已初始化
        await self.vector_service.ensure_initialized(self.load_index_batch)
        
        # 如果没有指定 since，从 collection metadata 中读取上次同步时间
        if since is None:
            since = await self.vector_service.get_last_sync_time()
            if since is None:
                # 如果还没有同步过，默认从 24 小时前开始
                since = datetime.now() - timedelta(hours=24)
                app_logger.info("未找到上次同步时间，默认从 24 小时前开始同步")
        
        # 分批获取并同步变更的商品，避免大量变更时丢失数据
        total_synced = 0
        batch_size = 1000
        current_since = since
        
        while True:
            # 获取一批变更的商品 ID
            async with self.session_factory() as db:
                changed_ids = await GoodsDataService.get_changed_products(
                    db, since=current_since, limit=batch_size
                )
            
            if not changed_ids:
                break
            
            app_logger.info("检测到 {} 个变更商品，开始增量同步（since={}）", len(changed_ids), current_since)
            
            # 获取这些商品的索引文档
            async with self.session_factory() as db:
                documents = await GoodsDataService.get_index_documents(db, changed_ids)
            
            if not documents:
                app_logger.warning("变更商品中没有可索引的上架商品")
                break
            
            # 增量同步到 ChromaDB，并保存同步时间
            sync_time = datetime.now()
            synced_count = await self.vector_service.sync_incremental(documents, sync_time)
            total_synced += synced_count
            app_logger.info("本批同步完成，同步了 {} 个商品", synced_count)
            
            # 如果本批不足 batch_size，说明已经同步完所有变更
            if len(changed_ids) < batch_size:
                break
            
            # 更新 current_since 为本批最后一个商品的 updated_at，继续下一批
            # 由于 get_changed_products 按 updated_at 排序，取本批最后一个 ID 对应的 updated_at
            async with self.session_factory() as db:
                from sqlalchemy import text as sql_text
                result = await db.execute(
                    sql_text("SELECT updated_at FROM goods_products WHERE id = :id"),
                    {"id": changed_ids[-1]}
                )
                row = result.fetchone()
                if row:
                    current_since = row[0]
                else:
                    break
        
        if total_synced > 0:
            app_logger.info("增量同步全部完成，共同步了 {} 个商品", total_synced)
        else:
            app_logger.debug("没有需要同步的变更商品")
        
        return total_synced

    async def _resolve_brand(
        self, brand: str, **context: JsonValue
    ) -> tuple[int | None, JsonValue, dict[str, JsonValue] | None]:
        """解析品牌约束；不存在或有歧义时返回可直接回复的工具结果。"""
        # 品牌解析结束后关闭事务，向量和模型请求不占用这条数据库连接。
        async with self.session_factory() as db:
            brands = await GoodsDataService.resolve_brands(db, brand)
        if not brands:
            return None, None, self._result([], reason="brand_not_found", brand=brand, **context)
        if len(brands) > 1:
            return None, None, self._result(
                [],
                reason="brand_ambiguous",
                brand=brand,
                brand_candidates=[item.model_dump(mode="json") for item in brands],
                **context,
            )
        return brands[0].id, brands[0].model_dump(mode="json"), None

    async def search_products(self, query: str, brand: str | None = None) -> dict[str, JsonValue]:
        """
        混合检索：向量搜索 + 关键词搜索，使用 RRF 融合排序。

        向量搜索擅长语义理解，关键词搜索擅长精确匹配，两者结合提升召回质量。
        """
        brand_id = None
        brand_data = None
        if brand is not None:
            brand_id, brand_data, error = await self._resolve_brand(brand, query=query)
            if error is not None:
                return error

        # 并发执行向量搜索和关键词搜索
        await self.vector_service.ensure_initialized(self.load_index_batch)

        async def vector_search():
            hits = await self.vector_service.search(
                query, brand_id=brand_id, top_k=settings.GOODS_SEARCH_TOP_K * 2
            )
            return [hit.product_id for hit in hits]

        async def keyword_search():
            async with self.session_factory() as db:
                products = await GoodsDataService.keyword_search(
                    db, query, brand_id=brand_id, limit=settings.GOODS_SEARCH_TOP_K * 2
                )
            return [p.product_id for p in products]

        # 并发执行两种搜索
        import asyncio
        vector_ids, keyword_ids = await asyncio.gather(
            vector_search(), keyword_search(), return_exceptions=True
        )
        # 处理异常
        if isinstance(vector_ids, Exception):
            vector_ids = []
        if isinstance(keyword_ids, Exception):
            keyword_ids = []

        # RRF (Reciprocal Rank Fusion) 融合排序
        # 公式: score = sum(1 / (k + rank_i))，k 通常取 60
        K = 60
        product_scores: dict[int, float] = {}

        for rank, pid in enumerate(vector_ids):
            if isinstance(pid, int):
                product_scores[pid] = product_scores.get(pid, 0) + 1.0 / (K + rank + 1)

        for rank, pid in enumerate(keyword_ids):
            if isinstance(pid, int):
                product_scores[pid] = product_scores.get(pid, 0) + 1.0 / (K + rank + 1)

        # 按融合分数排序
        sorted_ids = [pid for pid, _ in sorted(product_scores.items(), key=lambda x: -x[1])]
        sorted_ids = sorted_ids[: settings.GOODS_SEARCH_TOP_K]

        if not sorted_ids:
            return self._result([], query=query, brand=brand_data, reason="no_match")

        async with self.session_factory() as db:
            products = await GoodsDataService.get_products(db, sorted_ids, brand_id=brand_id)

        # 下架商品已由数据服务排除；没有在售规格的商品不作为推荐候选。
        products = [product for product in products if product.availability != "no_active_skus"]
        products = products[: settings.GOODS_SEARCH_RESULT_LIMIT]
        return self._result(
            products, query=query, brand=brand_data, reason=None if products else "no_match"
        )

    async def search_products_by_price(
        self,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        brand: str | None = None,
        product_ids: list[int] | None = None,
    ) -> dict[str, JsonValue]:
        """按价格区间筛选在售商品，价格事实始终以本轮 MySQL 查询为准。"""
        # 价格边界与 SKU 售价一致，序列化为两位小数字符串，避免浮点误差。
        price_context: dict[str, JsonValue] = {
            "min_price": format(min_price, ".2f") if min_price is not None else None,
            "max_price": format(max_price, ".2f") if max_price is not None else None,
        }
        brand_id = None
        brand_data = None
        if brand is not None:
            brand_id, brand_data, error = await self._resolve_brand(brand, **price_context)
            if error is not None:
                return error
        async with self.session_factory() as db:
            products = await GoodsDataService.get_products_by_price(
                db,
                min_price=min_price,
                max_price=max_price,
                brand_id=brand_id,
                product_ids=product_ids,
                limit=settings.GOODS_SEARCH_RESULT_LIMIT,
            )
        return self._result(
            products,
            brand=brand_data,
            reason=None if products else "no_match",
            **price_context,
        )

    async def get_product(self, product_id: int) -> dict[str, JsonValue]:
        """每次都查询当前商品数据，不把历史记录中的价格库存作为事实。"""
        async with self.session_factory() as db:
            product = await GoodsDataService.get_product(db, product_id)
        return self._result(
            [product] if product is not None else [],
            product_id=product_id,
            reason=None if product is not None else "not_available",
        )

    @staticmethod
    def _result(products: list[ProductDTO], **context: JsonValue) -> dict[str, JsonValue]:
        """限制工具结果体积，优先缩减描述和候选，不截断价格库存事实。"""
        serialized = [product.model_dump(mode="json") for product in products]
        truncated = False
        for product in serialized:
            description = product["description"]
            if len(description) > MAX_PRODUCT_DESCRIPTION_CHARS:
                product["description"] = description[:MAX_PRODUCT_DESCRIPTION_CHARS]
                truncated = True
        result: dict[str, JsonValue] = {
            "ok": True,
            "found": bool(serialized),
            "queried_at": TimeUtil.get_date().astimezone(ZoneInfo(settings.AGENT_TIMEZONE)).isoformat(),
            "products": serialized,
            **context,
        }

        def encoded_size() -> int:
            """按公共运行器实际采用的 JSON 编码计算字节数。"""
            return len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode())

        if encoded_size() > MAX_TOOL_RESULT_BYTES:
            for product in serialized:
                product["description"] = ""
            truncated = True
        while len(serialized) > 1 and encoded_size() > MAX_TOOL_RESULT_BYTES:
            serialized.pop()
            truncated = True
        if encoded_size() > MAX_TOOL_RESULT_BYTES:
            raise AppException(msg="商品规格信息过多，请缩小查询范围后重试")
        if truncated:
            result["truncated"] = True
        return result
