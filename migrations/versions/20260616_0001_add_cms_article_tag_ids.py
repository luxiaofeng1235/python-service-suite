"""
============================================
add tag_ids column to cms_articles
============================================

Add JSON tag_ids column to support article-tag association.

Revision ID: 20260616_0001_add_cms_article_tag_ids
Revises: 20260713_0001_add_auth_admin_and_admin_token_tables
Create Date: 2026-06-16 14:05:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "20260616_0001_add_cms_article_tag_ids"
down_revision: str | None = "20260713_0001_add_auth_admin_and_admin_token_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cms_articles",
        sa.Column("tag_ids", sa.JSON(), nullable=True, comment="关联标签ID列表"),
    )


def downgrade() -> None:
    op.drop_column("cms_articles", "tag_ids")
