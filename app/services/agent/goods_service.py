"""
============================================
商品智能体服务 - 语义召回与实时商品事实编排
============================================
以短数据库会话查询品牌和商品，复用公共会话、工具调用及流式响应机制。
向量库仅提供候选，售价、库存和上下架状态始终以本轮 MySQL 查询为准。
"""

import json
from collections.abc import AsyncIterator
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.goods import create_goods_agent
from app.agents.llm.base import LLMAdapter
from app.common.exception import AppException
from app.core.config import settings
from app.database import async_session
from app.schemas.agent.chat import AgentChatRequest, AgentStreamEvent
from app.schemas.agent.goods_data import IndexBatch, ProductDTO
from app.services.agent.chat_service import AgentChatService
from app.services.agent.goods_data_service import GoodsDataService
from app.services.agent.goods_vector_service import GoodsVectorService

MAX_TOOL_RESULT_BYTES = 55000
MAX_PRODUCT_DESCRIPTION_CHARS = 1000


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

    def _chat_service(self) -> AgentChatService:
        """复用公共聊天存储，由后台登录身份校验会话归属。"""
        runner = create_goods_agent(self.search_products, self.get_product, llm=self.llm)
        return AgentChatService(runner, session_factory=self.session_factory)

    async def stream_chat(
        self, req: AgentChatRequest, user_id: int
    ) -> AsyncIterator[AgentStreamEvent]:
        """按现有事件协议执行一次商品查询，退出时关闭底层生成器。"""
        self._check_enabled()
        stream = self._chat_service().stream_chat(req, user_id)
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

    async def search_products(self, query: str, brand: str | None = None) -> dict[str, JsonValue]:
        """解析品牌、语义召回，再使用当前 MySQL 数据核验候选。"""
        brand_id = None
        brand_data = None
        if brand is not None:
            # 品牌解析结束后关闭事务，向量和模型请求不占用这条数据库连接。
            async with self.session_factory() as db:
                brands = await GoodsDataService.resolve_brands(db, brand)
            if not brands:
                return self._result([], query=query, reason="brand_not_found", brand=brand)
            if len(brands) > 1:
                return self._result(
                    [],
                    query=query,
                    reason="brand_ambiguous",
                    brand=brand,
                    brand_candidates=[item.model_dump(mode="json") for item in brands],
                )
            brand_id = brands[0].id
            brand_data = brands[0].model_dump(mode="json")

        await self.vector_service.ensure_initialized(self.load_index_batch)
        hits = await self.vector_service.search(
            query, brand_id=brand_id, top_k=settings.GOODS_SEARCH_TOP_K
        )
        if not hits:
            return self._result([], query=query, brand=brand_data, reason="no_match")
        async with self.session_factory() as db:
            products = await GoodsDataService.get_products(
                db, [hit.product_id for hit in hits], brand_id=brand_id
            )
        # 下架商品已由数据服务排除；没有在售规格的商品不作为推荐候选。
        products = [product for product in products if product.availability != "no_active_skus"]
        products = products[: settings.GOODS_SEARCH_RESULT_LIMIT]
        return self._result(
            products, query=query, brand=brand_data, reason=None if products else "no_match"
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
            "queried_at": datetime.now(ZoneInfo(settings.AGENT_TIMEZONE)).isoformat(),
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
