"""
============================================
商品表初始化迁移 - 类目、品牌、商品与规格
============================================
补建商品 Agent 所需的四张表，结构与商品初始化 SQL 保持一致。
已有表直接跳过，保留手动导入的数据；迁移仅创建结构，不写入演示商品。
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20261112_0001"
down_revision: str | None = "20261111_0003"
branch_labels = None
depends_on = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    """每张表独立创建时间字段，插入默认当前时间，更新时自动刷新。"""
    return (
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            comment="更新时间",
        ),
    )


def upgrade() -> None:
    """只创建缺失的商品表及索引，兼容已经导入商品 SQL 的数据库。"""
    tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "goods_categories" not in tables:
        op.create_table(
            "goods_categories",
            sa.Column(
                "id",
                mysql.BIGINT(unsigned=True),
                primary_key=True,
                autoincrement=True,
                comment="类目ID",
            ),
            sa.Column("name", sa.String(50), nullable=False, comment="类目名称"),
            sa.Column(
                "parent_id",
                mysql.BIGINT(unsigned=True),
                nullable=True,
                comment="父级类目ID (NULL表示一级大类)",
            ),
            sa.Column(
                "sort_order",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
                comment="排序权重",
            ),
            *_timestamps(),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="商品类目表",
        )
        op.create_index("idx_parent_id", "goods_categories", ["parent_id"])

    if "goods_brands" not in tables:
        op.create_table(
            "goods_brands",
            sa.Column(
                "id",
                mysql.INTEGER(unsigned=True),
                primary_key=True,
                autoincrement=True,
                comment="品牌ID",
            ),
            sa.Column(
                "name", sa.String(100), nullable=False, server_default="", comment="品牌名称"
            ),
            sa.Column(
                "image", sa.String(255), nullable=False, server_default="", comment="品牌Logo图片"
            ),
            sa.Column(
                "initial", sa.CHAR(1), nullable=False, server_default="", comment="品牌首字母"
            ),
            sa.Column(
                "is_recommend",
                mysql.TINYINT(unsigned=True),
                nullable=False,
                server_default=sa.text("0"),
                comment="是否推荐：0否、1是",
            ),
            sa.Column(
                "sort",
                mysql.INTEGER(unsigned=True),
                nullable=False,
                server_default=sa.text("0"),
                comment="排序权重",
            ),
            sa.Column(
                "remark", sa.String(255), nullable=False, server_default="", comment="备注描述"
            ),
            *_timestamps(),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="商品品牌表",
        )
        op.create_index("idx_initial", "goods_brands", ["initial"])
        op.create_index("idx_sort", "goods_brands", ["sort"])

    if "goods_products" not in tables:
        op.create_table(
            "goods_products",
            sa.Column(
                "id",
                mysql.BIGINT(unsigned=True),
                primary_key=True,
                autoincrement=True,
                comment="SPU ID",
            ),
            sa.Column(
                "category_id",
                mysql.BIGINT(unsigned=True),
                nullable=False,
                comment="关联商品类目ID，对应goods_categories.id",
            ),
            sa.Column("name", sa.String(120), nullable=False, comment="商品名称"),
            sa.Column(
                "brand_id",
                mysql.INTEGER(unsigned=True),
                nullable=False,
                comment="关联商品品牌ID，对应goods_brands.id",
            ),
            sa.Column(
                "cover_image", sa.String(255), nullable=True, server_default="", comment="商品主图"
            ),
            sa.Column(
                "description", sa.Text(), nullable=True, comment="商品详细描述与卖点 (供Agent检索)"
            ),
            sa.Column(
                "status",
                mysql.TINYINT(),
                nullable=False,
                server_default=sa.text("1"),
                comment="状态: 0-下架, 1-上架",
            ),
            sa.Column(
                "spec_type",
                mysql.TINYINT(),
                nullable=False,
                server_default=sa.text("1"),
                comment="规格类型：1单规格、2多规格",
            ),
            *_timestamps(),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="商品SPU表",
        )
        op.create_index("idx_category_id", "goods_products", ["category_id"])
        op.create_index("idx_brand_id", "goods_products", ["brand_id"])

    if "goods_skus" not in tables:
        op.create_table(
            "goods_skus",
            sa.Column(
                "id",
                mysql.BIGINT(unsigned=True),
                primary_key=True,
                autoincrement=True,
                comment="SKU ID",
            ),
            sa.Column(
                "product_id",
                mysql.BIGINT(unsigned=True),
                nullable=False,
                comment="关联商品SPU ID，对应goods_products.id",
            ),
            sa.Column("sku_code", sa.String(64), nullable=False, comment="SKU唯一编码"),
            sa.Column(
                "spec_name", sa.String(100), nullable=False, comment="规格描述 (如: 黑色 / 256GB)"
            ),
            sa.Column("price", sa.Numeric(10, 2), nullable=False, comment="售价"),
            sa.Column(
                "stock",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
                comment="库存",
            ),
            sa.Column(
                "status",
                mysql.TINYINT(),
                nullable=False,
                server_default=sa.text("1"),
                comment="状态: 0-停售, 1-在售",
            ),
            *_timestamps(),
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
            comment="商品SKU表",
        )
        op.create_index("uk_sku_code", "goods_skus", ["sku_code"], unique=True)
        op.create_index("idx_product_id", "goods_skus", ["product_id"])


def downgrade() -> None:
    """无法区分既有商品表与本迁移新建的表，禁止自动删表以保留商品数据。"""
    raise RuntimeError("该迁移兼容已有商品表，不支持自动降级；请从备份恢复")
