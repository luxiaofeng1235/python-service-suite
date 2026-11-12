"""
============================================
商品共享数据模型 - 索引资料与实时查询结果
============================================
统一向量服务、商品查询服务和 Agent 之间的数据契约，不包含数据库操作。
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class GoodsDataModel(BaseModel):
    """限制共享数据字段，避免模块之间静默传递错误结构。"""

    model_config = ConfigDict(extra="forbid")


class BrandDTO(GoodsDataModel):
    """后端解析得到的品牌候选。"""

    id: int = Field(..., gt=0, description="品牌 ID")
    name: str = Field(..., description="数据库中的品牌名称")


class IndexDocument(GoodsDataModel):
    """可以向量化的商品资料，价格和库存必须另查 MySQL。"""

    product_id: int = Field(..., gt=0, description="商品 ID")
    brand_id: int = Field(..., gt=0, description="关联品牌 ID")
    category_id: int = Field(..., gt=0, description="关联类目 ID")
    name: str = Field(..., description="商品名称")
    brand_name: str = Field(..., description="关联品牌名称")
    category_name: str = Field(..., description="所属类目名称")
    category_path: list[str] = Field(default_factory=list, description="从父级到当前类目的名称路径")
    description: str = Field("", description="商品描述与卖点")
    updated_at: datetime = Field(..., description="商品资料更新时间")


class IndexBatch(GoodsDataModel):
    """按商品 ID 游标读取的一批索引资料。"""

    items: list[IndexDocument] = Field(default_factory=list, description="本批商品索引资料")
    next_after_id: int = Field(0, ge=0, description="下批查询使用的商品 ID 游标")
    has_more: bool = Field(False, description="是否还有下一批资料")


class VectorHit(GoodsDataModel):
    """语义召回的商品关联信息，距离越小越相关。"""

    product_id: int = Field(..., gt=0, description="候选商品 ID")
    distance: float = Field(..., allow_inf_nan=False, description="余弦距离")


class SkuDTO(GoodsDataModel):
    """本次数据库查询得到的在售 SKU。"""

    sku_id: int = Field(..., gt=0, description="SKU ID")
    sku_code: str = Field(..., description="SKU 编码")
    spec_name: str = Field(..., description="规格描述")
    price: Decimal = Field(..., ge=0, description="售价，JSON 输出保留两位小数")
    stock: int = Field(..., ge=0, description="本次查询的库存数量")

    @field_serializer("price", when_used="json")
    def serialize_price(self, value: Decimal) -> str:
        """使用十进制定点字符串，避免价格出现浮点误差。"""
        return format(value, ".2f")


class ProductDTO(GoodsDataModel):
    """本次查询得到的商品和规格事实。"""

    product_id: int = Field(..., gt=0, description="商品 ID")
    name: str = Field(..., description="商品名称")
    brand_id: int = Field(..., gt=0, description="关联品牌 ID")
    brand_name: str = Field(..., description="关联品牌名称")
    category_id: int = Field(..., gt=0, description="所属类目 ID")
    category_name: str = Field(..., description="所属类目名称")
    cover_image: str = Field("", description="商品主图地址或路径")
    description: str = Field("", description="商品描述与卖点")
    spec_type: Literal[1, 2] = Field(..., description="规格类型：1 单规格、2 多规格")
    availability: Literal["in_stock", "out_of_stock", "no_active_skus"] = Field(
        ..., description="可售状态：有货、全部缺货、没有在售规格"
    )
    queried_at: datetime = Field(..., description="本次商品事实查询时间，包含业务时区")
    skus: list[SkuDTO] = Field(default_factory=list, description="在售 SKU，保留库存为零的规格")
