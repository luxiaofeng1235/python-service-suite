"""
============================================
add tag_ids column to cms_articles
============================================

Add JSON tag_ids column to support article-tag association.

Revision ID: 20260616_0001_add_cms_article_tag_ids
Revises: 20260612_0001
Create Date: 2026-06-16 14:05:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "20260616_0001_add_cms_article_tag_ids"
down_revision: str | None = "20260612_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("cms_articles"):
        # 修复历史迁移缺少建表步骤的问题，保留原 revision 兼容已有环境。
        op.create_table(
            "cms_articles",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, comment="Article ID"),
            sa.Column("title", sa.String(255), nullable=False, comment="Article title"),
            sa.Column("slug", sa.String(255), nullable=False, unique=True, comment="URL slug"),
            sa.Column("category_id", sa.Integer(), nullable=False, index=True, comment="Category ID"),
            sa.Column("author", sa.String(100), nullable=True, comment="Author"),
            sa.Column("summary", sa.String(500), nullable=True, comment="Summary"),
            sa.Column("content", sa.Text(), nullable=False, comment="Article content"),
            sa.Column("cover_image", sa.String(255), nullable=True, comment="Cover image URL"),
            sa.Column("status", sa.SmallInteger(), nullable=False, server_default="0", comment="0=draft 1=published 2=offline"),
            sa.Column("view_count", sa.Integer(), nullable=False, server_default="0", comment="View count"),
            sa.Column("published_at", sa.DateTime(), nullable=True, comment="Published time"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="Created time"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="Updated time"),
            mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
        )
    columns = {column["name"] for column in sa.inspect(bind).get_columns("cms_articles")}
    if "tag_ids" not in columns:
        op.add_column(
            "cms_articles",
            sa.Column("tag_ids", sa.JSON(), nullable=True, comment="Associated tag IDs"),
        )


def downgrade() -> None:
    op.drop_column("cms_articles", "tag_ids")
