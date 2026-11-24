"""
============================================
商品工具参数 - 语义检索与实时规格查询
============================================
只开放商品查询参数，身份、索引维护和写入操作不交给模型控制。
"""

from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GoodsSearchToolRequest(BaseModel):
    """商品语义查询，可附带明确的品牌约束。"""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=500, description="商品需求或商品名称")
    brand: str | None = Field(
        None, min_length=1, max_length=100, description="用户明确指定的品牌名称"
    )

    @field_validator("query", "brand")
    @classmethod
    def validate_text(cls, value: str | None) -> str | None:
        """去掉首尾空白，拒绝空白查询和空白品牌。"""
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("商品查询词和品牌名称不能为空白")
        return value


class GoodsProductToolRequest(BaseModel):
    """通过可信商品 ID 查询当前规格、售价和库存。"""

    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(..., gt=0, strict=True, description="已知的商品 ID，不能凭空编造")


class GoodsPriceSearchToolRequest(BaseModel):
    """按售价区间筛选在售商品，可附带明确的品牌约束或限定商品范围。"""

    model_config = ConfigDict(extra="forbid")

    min_price: Decimal | None = Field(
        None, ge=0, max_digits=10, decimal_places=2, description="最低售价（元），包含边界"
    )
    max_price: Decimal | None = Field(
        None, ge=0, max_digits=10, decimal_places=2, description="最高售价（元），包含边界"
    )
    brand: str | None = Field(
        None, min_length=1, max_length=100, description="用户明确指定的品牌名称"
    )
    product_ids: list[int] | None = Field(
        None, description="限定商品 ID 范围，用于在语义搜索结果内按价格筛选，确保品类一致"
    )

    @field_validator("brand")
    @classmethod
    def validate_brand(cls, value: str | None) -> str | None:
        """去掉品牌首尾空白，拒绝空白品牌。"""
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("品牌名称不能为空白")
        return value

    @field_validator("product_ids")
    @classmethod
    def validate_product_ids(cls, value: list[int] | None) -> list[int] | None:
        """商品 ID 必须为正整数，数量不超过 100。"""
        if value is None:
            return value
        if not value:
            raise ValueError("商品 ID 列表不能为空")
        if len(value) > 100:
            raise ValueError("商品 ID 数量不能超过 100")
        if any(not isinstance(item, int) or isinstance(item, bool) or item <= 0 for item in value):
            raise ValueError("商品 ID 必须为正整数")
        return value

    @model_validator(mode="after")
    def validate_price_range(self) -> Self:
        """至少提供一个价格边界，且下限不能高于上限。"""
        if self.min_price is None and self.max_price is None:
            raise ValueError("至少提供最低价格或最高价格")
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError("最低价格不能高于最高价格")
        return self
