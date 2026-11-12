"""
============================================
商品数据服务 - 商品索引资料与实时规格查询
============================================
只读查询现有商品表，按召回顺序返回上架商品和在售规格，不执行商品写入。
数据库会话由调用方管理，每次工具调用和索引批次使用独立短会话。
"""

import re
import unicodedata
from collections.abc import Sequence
from datetime import datetime
from typing import ClassVar
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import Row, Select, and_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.core.config import settings
from app.models.goods import GoodsBrand, GoodsCategory, GoodsProduct, GoodsSku
from app.schemas.agent.goods_data import (
    BrandDTO,
    IndexBatch,
    IndexDocument,
    ProductDTO,
    SkuDTO,
)


class GoodsDataService:
    """集中维护商品只读查询、品牌解析和索引资料组装规则。"""

    MAX_PRODUCT_IDS = 100
    MAX_INDEX_BATCH_SIZE = 500
    MAX_CATEGORY_DEPTH = 64
    # 索引保留较完整卖点；工具摘要限制描述长度，避免挤占会话上下文。
    MAX_INDEX_DESCRIPTION_CHARS = 6000
    MAX_PRODUCT_DESCRIPTION_CHARS = 1200
    BRAND_ALIASES: ClassVar[dict[str, str]] = {"apple": "苹果"}

    @staticmethod
    async def get_index_batch(
        db: AsyncSession,
        *,
        after_id: int = 0,
        limit: int = 100,
    ) -> IndexBatch:
        """按商品 ID 游标读取在售商品，多读一条以判断是否存在下一批。"""
        if isinstance(after_id, bool) or not isinstance(after_id, int) or after_id < 0:
            raise AppException(msg="商品索引游标必须为非负整数")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= GoodsDataService.MAX_INDEX_BATCH_SIZE
        ):
            raise AppException(
                msg=f"商品索引批次大小必须在 1 到 {GoodsDataService.MAX_INDEX_BATCH_SIZE} 之间"
            )
        rows = await GoodsDataService._read_rows(
            db,
            GoodsDataService._index_statement()
            .where(GoodsProduct.id > after_id)
            .order_by(GoodsProduct.id.asc())
            .limit(limit + 1),
        )
        selected = rows[:limit]
        documents = await GoodsDataService._build_index_documents(db, selected)
        return IndexBatch(
            items=documents,
            next_after_id=documents[-1].product_id if documents else after_id,
            has_more=len(rows) > limit,
        )

    @staticmethod
    async def get_index_documents(
        db: AsyncSession,
        product_ids: list[int],
    ) -> list[IndexDocument]:
        """读取指定上架商品的索引资料，缺失或下架的 ID 不返回。"""
        ids = GoodsDataService._product_ids(product_ids)
        if not ids:
            return []
        rows = await GoodsDataService._read_rows(
            db,
            GoodsDataService._index_statement().where(GoodsProduct.id.in_(ids)),
        )
        documents = await GoodsDataService._build_index_documents(db, rows)
        by_id = {document.product_id: document for document in documents}
        return [by_id[product_id] for product_id in ids if product_id in by_id]

    @staticmethod
    async def resolve_brands(db: AsyncSession, name: str) -> list[BrandDTO]:
        """规范化品牌全名、括号别名和明确别名，歧义时保留所有候选。"""
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise AppException(msg="品牌名称不能为空且不能超过 100 个字符")
        normalized = GoodsDataService._normalize_brand(name)
        target = GoodsDataService.BRAND_ALIASES.get(normalized, normalized)
        rows = await GoodsDataService._read_rows(
            db,
            select(GoodsBrand.id, GoodsBrand.name).order_by(GoodsBrand.id.asc()),
        )
        candidates: list[BrandDTO] = []
        for brand_id, brand_name in rows:
            aliases = GoodsDataService._brand_names(brand_name)
            if target in aliases or normalized in aliases:
                candidates.append(BrandDTO(id=brand_id, name=brand_name))
        return candidates

    @staticmethod
    async def get_products(
        db: AsyncSession,
        product_ids: list[int],
        *,
        brand_id: int | None = None,
    ) -> list[ProductDTO]:
        """一次关联查询核验商品与 SKU，按输入 ID 顺序组装实时商品事实。"""
        ids = GoodsDataService._product_ids(product_ids)
        if brand_id is not None and (
            isinstance(brand_id, bool) or not isinstance(brand_id, int) or brand_id <= 0
        ):
            raise AppException(msg="品牌 ID 必须为正整数")
        if not ids:
            return []
        statement = (
            select(GoodsProduct, GoodsBrand.name, GoodsCategory.name, GoodsSku)
            .outerjoin(GoodsBrand, GoodsBrand.id == GoodsProduct.brand_id)
            .outerjoin(GoodsCategory, GoodsCategory.id == GoodsProduct.category_id)
            # 规格过滤放在关联条件中，保留没有在售规格的商品以明确告知用户。
            .outerjoin(
                GoodsSku,
                and_(GoodsSku.product_id == GoodsProduct.id, GoodsSku.status == 1),
            )
            .where(GoodsProduct.id.in_(ids), GoodsProduct.status == 1)
            .order_by(GoodsProduct.id.asc(), GoodsSku.id.asc())
            .execution_options(populate_existing=True)
        )
        if brand_id is not None:
            statement = statement.where(GoodsProduct.brand_id == brand_id)
        rows = await GoodsDataService._read_rows(db, statement)
        queried_at = datetime.now(ZoneInfo(settings.AGENT_TIMEZONE))
        products: dict[int, ProductDTO] = {}
        try:
            for product, brand_name, category_name, sku in rows:
                GoodsDataService._validate_related_names(brand_name, category_name)
                if product.id not in products:
                    products[product.id] = ProductDTO(
                        product_id=product.id,
                        name=product.name,
                        brand_id=product.brand_id,
                        brand_name=brand_name,
                        category_id=product.category_id,
                        category_name=category_name,
                        cover_image=product.cover_image or "",
                        description=(product.description or "")[
                            : GoodsDataService.MAX_PRODUCT_DESCRIPTION_CHARS
                        ],
                        spec_type=product.spec_type,
                        availability="no_active_skus",
                        queried_at=queried_at,
                    )
                result = products[product.id]
                if sku is not None:
                    result.skus.append(
                        SkuDTO(
                            sku_id=sku.id,
                            sku_code=sku.sku_code,
                            spec_name=sku.spec_name,
                            price=sku.price,
                            stock=sku.stock,
                        )
                    )
            for result in products.values():
                if result.skus:
                    result.availability = (
                        "in_stock" if any(sku.stock > 0 for sku in result.skus) else "out_of_stock"
                    )
        except ValidationError as exc:
            raise AppException(msg="商品或规格数据异常，请联系管理员") from exc
        return [products[product_id] for product_id in ids if product_id in products]

    @staticmethod
    async def get_product(db: AsyncSession, product_id: int) -> ProductDTO | None:
        """查询单个上架商品，不存在或下架时返回空值。"""
        products = await GoodsDataService.get_products(db, [product_id])
        return products[0] if products else None

    @staticmethod
    def _index_statement() -> Select:
        """索引读取也以 MySQL 上架状态为准，保留异常关联供显式检查。"""
        return (
            select(GoodsProduct, GoodsBrand.name, GoodsCategory.name)
            .outerjoin(GoodsBrand, GoodsBrand.id == GoodsProduct.brand_id)
            .outerjoin(GoodsCategory, GoodsCategory.id == GoodsProduct.category_id)
            .where(GoodsProduct.status == 1)
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def _build_index_documents(
        db: AsyncSession,
        rows: Sequence[Row],
    ) -> list[IndexDocument]:
        """批量读取类目映射，在内存中构建路径，避免逐商品查询父类目。"""
        if not rows:
            return []
        category_rows = await GoodsDataService._read_rows(
            db, select(GoodsCategory.id, GoodsCategory.name, GoodsCategory.parent_id)
        )
        categories = {
            category_id: (name, parent_id) for category_id, name, parent_id in category_rows
        }
        documents: list[IndexDocument] = []
        try:
            for product, brand_name, category_name in rows:
                GoodsDataService._validate_related_names(brand_name, category_name)
                documents.append(
                    IndexDocument(
                        product_id=product.id,
                        brand_id=product.brand_id,
                        category_id=product.category_id,
                        name=product.name,
                        brand_name=brand_name,
                        category_name=category_name,
                        category_path=GoodsDataService._category_path(
                            product.category_id, categories
                        ),
                        description=(product.description or "")[
                            : GoodsDataService.MAX_INDEX_DESCRIPTION_CHARS
                        ],
                        updated_at=product.updated_at,
                    )
                )
        except ValidationError as exc:
            raise AppException(msg="商品索引资料异常，请联系管理员") from exc
        return documents

    @staticmethod
    def _category_path(
        category_id: int,
        categories: dict[int, tuple[str, int | None]],
    ) -> list[str]:
        """构建从根类目到当前类目的路径，遇到缺失、环或异常深度时终止。"""
        path: list[str] = []
        visited: set[int] = set()
        current_id: int | None = category_id
        while current_id is not None:
            if current_id in visited or len(path) >= GoodsDataService.MAX_CATEGORY_DEPTH:
                raise AppException(msg="商品类目层级异常，请联系管理员")
            category = categories.get(current_id)
            if category is None or not category[0]:
                raise AppException(msg="商品类目关联异常，请联系管理员")
            visited.add(current_id)
            path.append(category[0])
            current_id = category[1]
        return list(reversed(path))

    @staticmethod
    def _product_ids(product_ids: list[int]) -> list[int]:
        """限制查询范围并去重，保持调用方给定的语义召回排序。"""
        if len(product_ids) > GoodsDataService.MAX_PRODUCT_IDS:
            raise AppException(msg=f"单次最多查询 {GoodsDataService.MAX_PRODUCT_IDS} 个商品")
        if any(
            isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in product_ids
        ):
            raise AppException(msg="商品 ID 必须为正整数")
        return list(dict.fromkeys(product_ids))

    @staticmethod
    def _normalize_brand(name: str) -> str:
        """统一全半角、大小写及空白，不做模糊猜测或品牌 ID 硬编码。"""
        return "".join(unicodedata.normalize("NFKC", name).casefold().split())

    @staticmethod
    def _brand_names(name: str) -> set[str]:
        """从品牌全名提取主名称及括号中的明确别名。"""
        normalized = GoodsDataService._normalize_brand(name)
        parts = re.findall(r"[^()]+", normalized)
        return {normalized, *parts}

    @staticmethod
    def _validate_related_names(brand_name: str | None, category_name: str | None) -> None:
        """缺失品牌或类目关联属于数据错误，不能伪装成商品不存在。"""
        if (
            not brand_name
            or not brand_name.strip()
            or not category_name
            or not category_name.strip()
        ):
            raise AppException(msg="商品品牌或类目关联异常，请联系管理员")

    @staticmethod
    async def _read_rows(db: AsyncSession, statement: Select) -> Sequence[Row]:
        """读取查询结果，屏蔽数据库内部错误细节，不提交或修改调用方事务。"""
        try:
            return (await db.execute(statement)).all()
        except SQLAlchemyError as exc:
            raise AppException(msg="商品数据查询失败，请稍后重试") from exc
