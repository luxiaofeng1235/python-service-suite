"""add user soft delete (is_deleted, deleted_at)

Revision ID: 20260528_0003
Revises: 20260528_0002
Create Date: 2026-05-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260528_0003"
down_revision: Union[str, None] = "20260528_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("users", "is_deleted"):
        op.add_column(
            "users",
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
                comment="是否已注销（软删除）",
            ),
        )
    if not _has_column("users", "deleted_at"):
        op.add_column(
            "users",
            sa.Column(
                "deleted_at",
                sa.DateTime(),
                nullable=True,
                comment="注销时间",
            ),
        )


def downgrade() -> None:
    if _has_column("users", "deleted_at"):
        op.drop_column("users", "deleted_at")
    if _has_column("users", "is_deleted"):
        op.drop_column("users", "is_deleted")
