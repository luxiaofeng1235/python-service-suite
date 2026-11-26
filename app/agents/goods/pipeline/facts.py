"""
============================================
商品事实格式化 - 工具结果解析与输出 formatting
============================================
解析工具返回的 JSON 结果，校验商品事实结构，
格式化价格库存文本，生成无匹配时的兜底答复。
"""

import json

from pydantic import JsonValue, ValidationError

from app.schemas.agent.goods_data import ProductDTO

MAX_FACT_TEXT_BYTES = 40000
MAX_SUMMARY_DESCRIPTION_CHARS = 500
MAX_SUMMARY_SPECIFICATIONS = 10


class FactsFormatter:
    """商品事实解析、格式化与兜底答复。"""

    @staticmethod
    def read_result(message) -> dict[str, JsonValue] | None:
        """只认可后台工具的成功 JSON 包装，不把异常当作空商品。"""
        if message is None or not message.content:
            return None
        try:
            result = json.loads(message.content)
        except (ValueError, TypeError):
            return None
        if not isinstance(result, dict) or result.get("ok") is not True:
            return None
        return result

    @staticmethod
    def read_products(result: dict[str, JsonValue]) -> list[ProductDTO]:
        """验证商品事实结构，防止错误的工具返回放开输出门禁。"""
        if result.get("found") is not True or not isinstance(result.get("products"), list):
            return []
        try:
            return [ProductDTO.model_validate(product) for product in result["products"]]
        except ValidationError:
            return []

    @staticmethod
    def fallback(outcomes: list[dict[str, JsonValue]]) -> str:
        """没有本轮商品事实时使用确定性答复，禁止让模型填补缺失数据。"""
        if not outcomes:
            return "我可以帮助查询商品。当前尚未取得有效商品数据，无法确认售价和库存，请提供商品名称或商品 ID 后重试。"
        reason = outcomes[-1].get("reason")
        if reason == "brand_ambiguous":
            candidates = outcomes[-1].get("brand_candidates")
            if isinstance(candidates, list):
                names = [
                    item["name"]
                    for item in candidates
                    if isinstance(item, dict) and isinstance(item.get("name"), str)
                ]
                return "品牌名称存在多个匹配，请明确选择：" + "、".join(names) + "。"
        if reason == "brand_not_found":
            return "未找到该品牌，请确认品牌名称后重新查询。"
        if reason == "not_available":
            return "该商品不存在或已下架，暂时无法提供当前售价和库存。"
        if reason == "no_match":
            return "未找到符合条件的在售商品，请换一个商品名称或需求描述。"
        return "商品查询暂时未取得有效数据，无法确认当前售价和库存，请稍后重试。"

    @staticmethod
    def format_facts(products: list[ProductDTO]) -> str:
        """后端直接格式化本轮价格库存，超长时明确提示省略规格。"""
        lines = ["\n\n本轮查询的商品规格与售价库存："]
        used_bytes = len(lines[0].encode())
        for product in products:
            header = (
                f"\n- 商品 ID {product.product_id}：{product.name}（品牌：{product.brand_name}）"
            )
            if product.availability == "no_active_skus":
                header += "，暂无在售规格。"
            elif product.availability == "out_of_stock":
                header += "，全部在售规格暂时缺货。"
            header += f"\n  查询时间：{product.queried_at.isoformat()}"
            if used_bytes + len(header.encode()) > MAX_FACT_TEXT_BYTES:
                lines.append("\n部分商品信息较多，请指定商品 ID 进一步查询。")
                break
            lines.append(header)
            used_bytes += len(header.encode())
            for sku in product.skus:
                line = (
                    f"\n  - {sku.spec_name}（SKU {sku.sku_id}）：¥{sku.price:.2f}，库存 {sku.stock}"
                )
                if used_bytes + len(line.encode()) > MAX_FACT_TEXT_BYTES:
                    lines.append("\n部分规格未展示，请缩小查询范围。")
                    return "".join(lines)
                lines.append(line)
                used_bytes += len(line.encode())
        return "".join(lines)

    @staticmethod
    def build_descriptions(products: list[ProductDTO]) -> list[dict]:
        """构建总结阶段的商品描述 JSON 列表。"""
        return [
            {
                "product_id": product.product_id,
                "name": product.name,
                "brand_name": product.brand_name,
                "category_name": product.category_name,
                "description": product.description[:MAX_SUMMARY_DESCRIPTION_CHARS],
                "spec_type": product.spec_type,
                "specifications": [
                    sku.spec_name for sku in product.skus[:MAX_SUMMARY_SPECIFICATIONS]
                ],
            }
            for product in products
        ]
