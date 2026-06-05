"""add auth_admin profile fields (avatar, mobile, email, sex, remark)

Revision ID: 20260605_0001
Revises: 20261201_0001
Create Date: 2026-06-05 01:40:00.000000+00:00

!!! This migration is IDEMPOTENT — safe to re-run on an already-migrated DB.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260605_0001"
down_revision: Union[str, None] = "20261201_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 获取当前表的字段名集合
    existing_columns = {c["name"] for c in inspector.get_columns("auth_admins")}

    additions = [
        ("avatar", sa.String(500), {"comment": "头像URL", "after": "nickname"}),
        ("mobile", sa.String(20), {"comment": "手机号", "after": "avatar"}),
        ("email", sa.String(255), {"comment": "邮箱", "after": "mobile"}),
        ("sex", sa.Integer(), {"server_default": "0", "comment": "性别 0=保密 1=男 2=女", "after": "email"}),
        ("remark", sa.String(500), {"comment": "备注", "after": "sex"}),
    ]

    for col_name, col_type, kwargs in additions:
        if col_name not in existing_columns:
            op.add_column("auth_admins", sa.Column(col_name, col_type, **kwargs))


def downgrade() -> None:
    op.drop_column("auth_admins", "remark")
    op.drop_column("auth_admins", "sex")
    op.drop_column("auth_admins", "email")
    op.drop_column("auth_admins", "mobile")
    op.drop_column("auth_admins", "avatar")
