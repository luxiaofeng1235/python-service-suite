"""drop users.is_super (no longer needed after RBAC migration)

Revision ID: 20261201_0001
Revises: 20260601_0001
Create Date: 2026-12-01

Reason: is_super on the frontend users table has no authentication purpose
after the RBAC migration — all admin auth now uses auth_admins.is_super + Casbin.
Removing it eliminates the semantic confusion of two is_super fields in the codebase.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261201_0001"
down_revision: Union[str, None] = "20260601_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if _has_column("users", "is_super"):
        op.drop_column("users", "is_super")


def downgrade() -> None:
    if not _has_column("users", "is_super"):
        op.add_column(
            "users",
            sa.Column(
                "is_super",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
                comment="是否管理员（仅用于旧版前端鉴权，已废弃）",
            ),
        )
