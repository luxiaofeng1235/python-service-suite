"""
============================================
商品向量服务 - 本地索引维护与语义召回
============================================
管理 Chroma 持久化集合，通过完整代发布隔离首次导入和重建中的半成品。
仅保存静态检索资料，商品上下架、价格和库存交由 MySQL 服务实时核验。
"""

import asyncio
import functools
import html
import math
import re
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypeVar

from app.agents.llm.embedding import EmbeddingAdapter, QwenEmbedding, validate_embedding
from app.common.exception import AppException
from app.core.config import settings
from app.pkg.logging import app_logger
from app.schemas.agent.goods_data import IndexBatch, IndexDocument, VectorHit

if TYPE_CHECKING:
    from chromadb.api import ClientAPI
    from chromadb.api.models.Collection import Collection


T = TypeVar("T")


class IndexBatchLoader(Protocol):
    """提供已结束数据库读取事务的一批商品资料。"""

    async def __call__(self, *, after_id: int, limit: int) -> IndexBatch:
        """按商品 ID 游标读取，返回数据后不保留数据库事务。"""
        ...


class GoodsVectorService:
    """同一路径仅允许一个进程实例维护，所有 Chroma 操作在专用线程串行执行。"""

    METRIC = "cosine"
    MAX_QUERY_RESULTS = 100
    MAX_DOCUMENT_CHARACTERS = 6000

    def __init__(
        self,
        *,
        embedding: EmbeddingAdapter | None = None,
        path: str | Path | None = None,
        collection: str | None = None,
    ) -> None:
        """保存配置；构造和导入模块不会创建目录、连接向量库或下载模型。"""
        self.embedding = embedding if embedding is not None else QwenEmbedding()
        self.path = Path(path if path is not None else settings.GOODS_CHROMA_PATH)
        self.collection_name = collection or settings.GOODS_CHROMA_COLLECTION
        self._fingerprint = {
            "embedding_model": settings.QWEN_EMBEDDING_MODEL,
            "dimensions": settings.QWEN_EMBEDDING_DIMENSIONS,
            "metric": self.METRIC,
            "schema_version": settings.GOODS_INDEX_SCHEMA_VERSION,
        }
        self._client: ClientAPI | None = None
        self._active: Collection | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._operation_slots = asyncio.Semaphore(4)
        self._maintenance_lock = asyncio.Lock()
        self._opened = False
        self._closed = False

    async def ensure_initialized(self, load_batch: IndexBatchLoader) -> None:
        """复用匹配的完整索引，首次或半成品失败后重新构建完整一代。"""
        if self._closed:
            raise AppException(msg="商品向量服务已关闭")
        if self._active is not None:
            return
        async with self._maintenance_lock:
            if self._active is not None:
                return
            await self._run_sync(self._open)
            if self._active is None:
                await self._build(load_batch)

    async def rebuild(self, load_batch: IndexBatchLoader) -> None:
        """在新集合构建索引，失败或取消时保留原来的完整索引。"""
        async with self._maintenance_lock:
            await self._run_sync(self._open)
            await self._build(load_batch)

    async def search(
        self,
        query: str,
        *,
        brand_id: int | None = None,
        top_k: int | None = None,
    ) -> list[VectorHit]:
        """返回按余弦距离排序的 ID，空结果与索引故障分别处理。"""
        collection = self._require_active()
        if not isinstance(query, str) or not query.strip():
            raise AppException(msg="商品搜索内容不能为空")
        if brand_id is not None and (type(brand_id) is not int or brand_id <= 0):
            raise AppException(msg="商品品牌参数错误")
        limit = settings.GOODS_SEARCH_TOP_K if top_k is None else top_k
        if type(limit) is not int or limit <= 0:
            raise AppException(msg="商品召回数量配置错误")
        limit = min(limit, self.MAX_QUERY_RESULTS)
        threshold = settings.GOODS_SEARCH_MAX_DISTANCE
        if not math.isfinite(threshold) or not 0 <= threshold <= 2:
            raise AppException(msg="商品相关性阈值配置错误")

        count = await self._run_sync(collection.count)
        if count == 0:
            return []
        vector = validate_embedding(
            await self.embedding.embed_query(query.strip()),
            settings.QWEN_EMBEDDING_DIMENSIONS,
        )
        return await self._run_sync(
            self._query,
            collection,
            vector,
            brand_id,
            min(limit, count),
            threshold,
        )

    async def upsert(self, documents: Sequence[IndexDocument]) -> None:
        """内部覆盖索引资料，不写商品数据库，不作为商品修改接口。"""
        if not documents:
            return
        async with self._maintenance_lock:
            async with self._copy_for_update() as collection:
                await self._upsert_documents(collection, documents)

    async def delete(self, product_ids: Sequence[int]) -> None:
        """内部移除下架或已删除商品的向量，重复删除保持幂等。"""
        if not product_ids:
            return
        if any(type(value) is not int or value <= 0 for value in product_ids):
            raise AppException(msg="商品索引 ID 错误")
        async with self._maintenance_lock:
            async with self._copy_for_update() as collection:
                ids = [f"prod_{value}" for value in dict.fromkeys(product_ids)]
                await self._run_sync(collection.delete, ids=ids)

    async def aclose(self) -> None:
        """停止新操作并等待已提交的同步操作结束，不假设取消能停止线程。"""
        self._closed = True
        async with self._maintenance_lock:
            executor = self._executor
            self._executor = None
            if executor is not None:
                await asyncio.to_thread(executor.shutdown, wait=True, cancel_futures=True)
            self._active = None
            self._client = None

    @asynccontextmanager
    async def _copy_for_update(self) -> AsyncIterator["Collection"]:
        """复制已有向量后维护新代，失败时不暴露半批覆盖，也不重新向量化旧商品。"""
        source = self._require_active()
        abandoned = threading.Event()
        try:
            async with asyncio.timeout(settings.GOODS_INDEX_TIMEOUT):
                target = await self._run_sync(self._create_generation)
                await self._run_sync(self._copy_generation, source, target, abandoned)
                yield target
                count = await self._run_sync(target.count)
                await self._run_sync(self._publish, target, count, abandoned)
                self._active = target
        except TimeoutError as exc:
            raise AppException(msg="商品索引同步超时，请稍后重试") from exc
        finally:
            abandoned.set()

    async def _build(self, load_batch: IndexBatchLoader) -> None:
        """导入全部批次后才标记完成，数据提供方每批自行结束数据库事务。"""
        batch_size = settings.GOODS_INDEX_BATCH_SIZE
        if batch_size <= 0 or settings.GOODS_INDEX_TIMEOUT <= 0:
            raise AppException(msg="商品索引批量或超时配置错误")
        abandoned = threading.Event()
        try:
            async with asyncio.timeout(settings.GOODS_INDEX_TIMEOUT):
                collection = await self._run_sync(self._create_generation)
                after_id = 0
                indexed_count = 0
                while True:
                    batch = await load_batch(after_id=after_id, limit=batch_size)
                    if not isinstance(batch, IndexBatch):
                        raise AppException(msg="商品索引批次格式错误")
                    ids = [item.product_id for item in batch.items]
                    if ids != sorted(set(ids)) or any(value <= after_id for value in ids):
                        raise AppException(msg="商品索引批次游标错误")
                    if batch.has_more and not ids:
                        raise AppException(msg="商品索引空批次不能继续翻页")
                    if ids and batch.next_after_id < ids[-1]:
                        raise AppException(msg="商品索引批次游标错误")
                    await self._upsert_documents(collection, batch.items)
                    indexed_count += len(batch.items)
                    if not batch.has_more:
                        break
                    if batch.next_after_id <= after_id:
                        raise AppException(msg="商品索引批次游标未前进")
                    after_id = batch.next_after_id
                # 取消在此之前到达时不会发布；线程中也会核对完整写入数量。
                await self._run_sync(self._publish, collection, indexed_count, abandoned)
                self._active = collection
                app_logger.info("商品向量索引已就绪，商品数量={}", indexed_count)
        except TimeoutError as exc:
            raise AppException(msg="商品索引初始化超时，请稍后重试") from exc
        finally:
            # 超时取消不会停止线程；尚未执行的发布操作必须识别本次构建已退出。
            abandoned.set()

    async def _upsert_documents(
        self,
        collection: "Collection",
        documents: Sequence[IndexDocument],
    ) -> None:
        """按模型批量限制处理文档，向量完全校验后再提交当前批次。"""
        batch_size = min(settings.GOODS_EMBEDDING_BATCH_SIZE, QwenEmbedding.MAX_BATCH_SIZE)
        if batch_size <= 0:
            raise AppException(msg="商品向量批量配置错误")
        ids = [item.product_id for item in documents]
        if len(ids) != len(set(ids)):
            raise AppException(msg="商品索引包含重复 ID")
        for offset in range(0, len(documents), batch_size):
            batch = list(documents[offset : offset + batch_size])
            texts = [self._document_text(item) for item in batch]
            vectors = await self.embedding.embed_documents(texts)
            if len(vectors) != len(batch):
                raise AppException(msg="商品文档与返回向量数量不一致")
            checked = [
                validate_embedding(vector, settings.QWEN_EMBEDDING_DIMENSIONS) for vector in vectors
            ]
            await self._run_sync(
                collection.upsert,
                ids=[f"prod_{item.product_id}" for item in batch],
                embeddings=checked,
                documents=texts,
                metadatas=[
                    {
                        "product_id": item.product_id,
                        "brand_id": item.brand_id,
                        "category_id": item.category_id,
                    }
                    for item in batch
                ],
            )

    def _open(self) -> None:
        """延迟连接本地库，只选择配置和数量均匹配的已完成集合。"""
        if self._opened:
            return
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,180}[A-Za-z0-9]", self.collection_name):
            raise AppException(msg="商品向量集合名称配置错误")
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError as exc:
            raise AppException(msg="商品向量依赖未安装，请安装项目依赖") from exc
        if self._client is None:
            self.path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(self.path.resolve()),
                settings=Settings(anonymized_telemetry=False),
            )
        candidates: list[tuple[int, Collection]] = []
        generations: list[tuple[int, Collection]] = []
        for item in self._client.list_collections():
            name = item if isinstance(item, str) else item.name
            if not name.startswith(f"{self.collection_name}__g_"):
                continue
            collection = self._client.get_collection(name, embedding_function=None)
            metadata = collection.metadata or {}
            generation = metadata.get("generation")
            if not isinstance(generation, str) or not generation.isdecimal():
                continue
            generations.append((int(generation), collection))
            if metadata.get("ready") is not True:
                continue
            if any(metadata.get(key) != value for key, value in self._fingerprint.items()):
                continue
            if metadata.get("indexed_count") != collection.count():
                continue
            candidates.append((int(generation), collection))
        if candidates:
            self._active = max(candidates, key=lambda item: item[0])[1]
        # 仅首次连接清理，此时同一进程尚无在途查询。运行期间保留旧代到下次启动。
        self._cleanup_generations(generations)
        self._opened = True

    def _create_generation(self) -> "Collection":
        """创建新的未完成集合，不复用失败集合，避免残留已下架商品。"""
        if self._client is None:
            raise AppException(msg="商品向量库尚未连接")
        generation = str(time.time_ns())
        return self._client.create_collection(
            name=f"{self.collection_name}__g_{generation}_{uuid.uuid4().hex[:8]}",
            embedding_function=None,
            metadata={**self._fingerprint, "ready": False, "generation": generation},
            configuration={"hnsw": {"space": self.METRIC}},
        )

    def _publish(
        self,
        collection: "Collection",
        expected_count: int,
        abandoned: threading.Event,
    ) -> None:
        """核验数量并提交完成标记；半成品永远不具备可加载的标记。"""
        if self._closed or abandoned.is_set():
            raise AppException(msg="商品索引构建已结束，本次结果未发布")
        if collection.count() != expected_count:
            raise AppException(msg="商品索引数量不一致，请重新初始化")
        if abandoned.is_set():
            raise AppException(msg="商品索引构建已结束，本次结果未发布")
        collection.modify(
            metadata={
                **(collection.metadata or {}),
                "ready": True,
                "indexed_count": expected_count,
            }
        )

    @staticmethod
    def _copy_generation(
        source: "Collection",
        target: "Collection",
        abandoned: threading.Event,
    ) -> None:
        """分批复制已经校验的向量，不在同步线程执行远程模型请求。"""
        count = source.count()
        for offset in range(0, count, settings.GOODS_INDEX_BATCH_SIZE):
            if abandoned.is_set():
                raise AppException(msg="商品索引同步已取消")
            batch = source.get(
                offset=offset,
                limit=settings.GOODS_INDEX_BATCH_SIZE,
                include=["documents", "metadatas", "embeddings"],
            )
            embeddings = batch.get("embeddings")
            documents = batch.get("documents")
            metadatas = batch.get("metadatas")
            ids = batch["ids"]
            if (
                embeddings is None
                or documents is None
                or metadatas is None
                or not len(ids) == len(embeddings) == len(documents) == len(metadatas)
                or any(value is None for value in documents)
                or any(value is None for value in metadatas)
            ):
                raise AppException(msg="已有商品索引数据不完整，请重建索引")
            target.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
                embeddings=embeddings,
            )
        if target.count() != count:
            raise AppException(msg="商品索引复制数量不一致，请重建索引")

    def _cleanup_generations(self, generations: list[tuple[int, "Collection"]]) -> None:
        """仅在启动时保留最近两代完整索引，并清除旧代和失败代。"""
        if self._client is None:
            return
        complete = [
            (generation, collection)
            for generation, collection in generations
            if (collection.metadata or {}).get("ready") is True
            and (collection.metadata or {}).get("indexed_count") == collection.count()
        ]
        recent = sorted(complete, reverse=True, key=lambda item: item[0])[:2]
        keep = {collection.name for _, collection in recent}
        if self._active is not None:
            keep.add(self._active.name)
        for _, collection in generations:
            if collection.name in keep:
                continue
            try:
                self._client.delete_collection(collection.name)
            except Exception as exc:
                app_logger.warning("旧商品索引清理失败，异常类型={}", type(exc).__name__)

    @staticmethod
    def _document_text(document: IndexDocument) -> str:
        """移除描述的 HTML 标记并控制长度，确保模型输入规模有界。"""
        description = html.unescape(re.sub(r"<[^>]+>", " ", document.description))
        description = " ".join(description.split())
        category = " / ".join(document.category_path) or document.category_name
        text = (
            f"商品名称：{document.name}\n品牌：{document.brand_name}\n"
            f"商品类目：{category}\n商品描述：{description}"
        )
        return text[: GoodsVectorService.MAX_DOCUMENT_CHARACTERS]

    @staticmethod
    def _query(
        collection: "Collection",
        vector: list[float],
        brand_id: int | None,
        limit: int,
        threshold: float,
    ) -> list[VectorHit]:
        """解析单条 query_embeddings 的嵌套结果，按距离去重并过滤阈值。"""
        result = collection.query(
            query_embeddings=[vector],
            n_results=limit,
            where={"brand_id": brand_id} if brand_id is not None else None,
            include=["metadatas", "distances"],
        )
        metadatas = result.get("metadatas")
        distances = result.get("distances")
        if not metadatas or not distances:
            return []
        if len(metadatas[0]) != len(distances[0]):
            raise AppException(msg="商品向量召回结果格式错误")
        hits: dict[int, VectorHit] = {}
        for metadata, raw_distance in zip(metadatas[0], distances[0], strict=True):
            if not isinstance(metadata, dict) or type(metadata.get("product_id")) is not int:
                raise AppException(msg="商品向量关联信息无效，请重建索引")
            if brand_id is not None and metadata.get("brand_id") != brand_id:
                continue
            distance = float(raw_distance)
            if not math.isfinite(distance):
                raise AppException(msg="商品向量距离无效")
            if distance > threshold:
                continue
            product_id = metadata["product_id"]
            if product_id not in hits or hits[product_id].distance > distance:
                hits[product_id] = VectorHit(product_id=product_id, distance=distance)
        return sorted(hits.values(), key=lambda item: (item.distance, item.product_id))

    def _require_active(self) -> "Collection":
        """区分未就绪与有效空库，防止把服务故障当作没有商品。"""
        if self._closed:
            raise AppException(msg="商品向量服务已关闭")
        if self._active is None:
            raise AppException(msg="商品索引尚未就绪，请稍后重试")
        return self._active

    async def _run_sync(self, function: Callable[..., T], *args: object, **kwargs: object) -> T:
        """有界提交至单线程；调用方取消后，槽位仍由真实线程完成时释放。"""
        if self._closed:
            raise AppException(msg="商品向量服务已关闭")
        await self._operation_slots.acquire()
        if self._closed:
            self._operation_slots.release()
            raise AppException(msg="商品向量服务已关闭")
        try:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="goods-chroma"
                )
            concurrent_future = self._executor.submit(functools.partial(function, *args, **kwargs))
        except BaseException:
            self._operation_slots.release()
            raise
        future = asyncio.wrap_future(concurrent_future)

        def completed(done: asyncio.Future[T]) -> None:
            """无论等待方是否已取消，都回收槽位并读取异步异常。"""
            self._operation_slots.release()
            if not done.cancelled():
                done.exception()

        future.add_done_callback(completed)
        try:
            return await asyncio.shield(future)
        except (AppException, asyncio.CancelledError):
            raise
        except Exception as exc:
            app_logger.warning("商品向量操作失败，异常类型={}", type(exc).__name__)
            raise AppException(msg="商品向量服务异常，请稍后重试") from exc
