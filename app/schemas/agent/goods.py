"""
============================================
商品工具参数 - 语义检索与实时规格查询
============================================
只开放商品查询参数，身份、索引维护和写入操作不交给模型控制。
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
