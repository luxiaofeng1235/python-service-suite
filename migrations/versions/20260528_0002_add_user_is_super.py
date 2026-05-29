"""add user is_super

Revision ID: 20260528_0002
Revises: 20260528_0001
Create Date: 2026-05-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260528_0002"
down_revision: Union[str, None] = "20260528_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("users", "is_super"):
        op.add_column(
            "users",
            sa.Column(
                "is_super",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
                comment="是否管理员",
            ),
        )


def downgrade() -> None:
    if _has_column("users", "is_super"):
        op.drop_column("users", "is_super")
