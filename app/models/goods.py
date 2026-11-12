"""
============================================
商品数据库模型 - 类目、品牌、商品与规格映射
============================================
严格映射现有商品 SQL 结构，为只读商品查询和向量索引提供数据访问模型。
"""

from sqlalchemy import (
    CHAR,
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.mysql import BIGINT, INTEGER, TINYINT

from app.database import Base


def _table_options(comment: str) -> dict[str, str]:
    """与商品初始化 SQL 使用相同的存储引擎、字符集和排序规则。"""
    return {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_unicode_ci",
        "comment": comment,
    }


class GoodsCategory(Base):
    """商品类目表，parent_id 为空时表示一级类目。"""

    __tablename__ = "goods_categories"
    __table_args__ = (
        Index("idx_parent_id", "parent_id"),
        _table_options("商品类目表"),
    )

    id = Column(
        BigInteger().with_variant(BIGINT(unsigned=True), "mysql"),
        primary_key=True,
        autoincrement=True,
        comment="类目ID",
    )
    name = Column(String(50), nullable=False, comment="类目名称")
    parent_id = Column(
        BigInteger().with_variant(BIGINT(unsigned=True), "mysql"),
        nullable=True,
        comment="父级类目ID (NULL表示一级大类)",
    )
    sort_order = Column(Integer, nullable=False, server_default=text("0"), comment="排序权重")
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="创建时间",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
        comment="更新时间",
    )

    def __repr__(self) -> str:
        return f"<GoodsCategory(id={self.id}, name={self.name!r})>"


class GoodsBrand(Base):
    """商品品牌表，商品通过 brand_id 关联品牌。"""

    __tablename__ = "goods_brands"
    __table_args__ = (
        Index("idx_initial", "initial"),
        Index("idx_sort", "sort"),
        _table_options("商品品牌表"),
    )

    id = Column(
        Integer().with_variant(INTEGER(unsigned=True), "mysql"),
        primary_key=True,
        autoincrement=True,
        comment="品牌ID",
    )
    name = Column(String(100), nullable=False, server_default="", comment="品牌名称")
    image = Column(String(255), nullable=False, server_default="", comment="品牌Logo图片")
    initial = Column(CHAR(1), nullable=False, server_default="", comment="品牌首字母")
    is_recommend = Column(
        SmallInteger().with_variant(TINYINT(unsigned=True), "mysql"),
        nullable=False,
        server_default=text("0"),
        comment="是否推荐：0否、1是",
    )
    sort = Column(
        Integer().with_variant(INTEGER(unsigned=True), "mysql"),
        nullable=False,
        server_default=text("0"),
        comment="排序权重",
    )
    remark = Column(String(255), nullable=False, server_default="", comment="备注描述")
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="创建时间",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
        comment="更新时间",
    )

    def __repr__(self) -> str:
        return f"<GoodsBrand(id={self.id}, name={self.name!r})>"


class GoodsProduct(Base):
    """商品主表，status 和 spec_type 分别记录上架状态与规格类型。"""

    __tablename__ = "goods_products"
    __table_args__ = (
        Index("idx_category_id", "category_id"),
        Index("idx_brand_id", "brand_id"),
        _table_options("商品SPU表"),
    )

    id = Column(
        BigInteger().with_variant(BIGINT(unsigned=True), "mysql"),
        primary_key=True,
        autoincrement=True,
        comment="SPU ID",
    )
    category_id = Column(
        BigInteger().with_variant(BIGINT(unsigned=True), "mysql"),
        nullable=False,
        comment="关联商品类目ID，对应goods_categories.id",
    )
    name = Column(String(120), nullable=False, comment="商品名称")
    brand_id = Column(
        Integer().with_variant(INTEGER(unsigned=True), "mysql"),
        nullable=False,
        comment="关联商品品牌ID，对应goods_brands.id",
    )
    cover_image = Column(String(255), nullable=True, server_default="", comment="商品主图")
    description = Column(Text, nullable=True, comment="商品详细描述与卖点 (供Agent检索)")
    status = Column(
        SmallInteger().with_variant(TINYINT(), "mysql"),
        nullable=False,
        server_default=text("1"),
        comment="状态: 0-下架, 1-上架",
    )
    spec_type = Column(
        SmallInteger().with_variant(TINYINT(), "mysql"),
        nullable=False,
        server_default=text("1"),
        comment="规格类型：1单规格、2多规格",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="创建时间",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
        comment="更新时间",
    )

    def __repr__(self) -> str:
        return f"<GoodsProduct(id={self.id}, name={self.name!r})>"


class GoodsSku(Base):
    """商品规格表，价格和库存直接取自本次数据库查询。"""

    __tablename__ = "goods_skus"
    __table_args__ = (
        Index("uk_sku_code", "sku_code", unique=True),
        Index("idx_product_id", "product_id"),
        _table_options("商品SKU表"),
    )

    id = Column(
        BigInteger().with_variant(BIGINT(unsigned=True), "mysql"),
        primary_key=True,
        autoincrement=True,
        comment="SKU ID",
    )
    product_id = Column(
        BigInteger().with_variant(BIGINT(unsigned=True), "mysql"),
        nullable=False,
        comment="关联商品SPU ID，对应goods_products.id",
    )
    sku_code = Column(String(64), nullable=False, comment="SKU唯一编码")
    spec_name = Column(String(100), nullable=False, comment="规格描述 (如: 黑色 / 256GB)")
    price = Column(Numeric(10, 2), nullable=False, comment="售价")
    stock = Column(Integer, nullable=False, server_default=text("0"), comment="库存")
    status = Column(
        SmallInteger().with_variant(TINYINT(), "mysql"),
        nullable=False,
        server_default=text("1"),
        comment="状态: 0-停售, 1-在售",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="创建时间",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
        comment="更新时间",
    )

    def __repr__(self) -> str:
        return f"<GoodsSku(id={self.id}, product_id={self.product_id}, sku_code={self.sku_code!r})>"
