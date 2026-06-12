"""add attachment owner fields

Revision ID: 20260612_0001
Revises: 20260605_0001
Create Date: 2026-06-12 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260612_0001"
down_revision: str | None = "20260605_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {c["name"] for c in inspector.get_columns("attachment")}
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("attachment")}

    if "owner_type" not in existing_columns:
        op.add_column(
            "attachment",
            sa.Column(
                "owner_type",
                sa.String(20),
                nullable=False,
                server_default="user",
                comment="归属类型：user/admin/system",
            ),
        )

    if "owner_id" not in existing_columns:
        op.add_column(
            "attachment",
            sa.Column(
                "owner_id",
                sa.Integer(),
                nullable=False,
                server_default="0",
                comment="归属主体ID",
            ),
        )
        op.execute("UPDATE attachment SET owner_id = user_id WHERE owner_id = 0")

    if "ix_attachment_owner_type" not in existing_indexes:
        op.create_index("ix_attachment_owner_type", "attachment", ["owner_type"], unique=False)

    if "ix_attachment_owner_id" not in existing_indexes:
        op.create_index("ix_attachment_owner_id", "attachment", ["owner_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {c["name"] for c in inspector.get_columns("attachment")}
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("attachment")}

    if "ix_attachment_owner_id" in existing_indexes:
        op.drop_index("ix_attachment_owner_id", table_name="attachment")

    if "ix_attachment_owner_type" in existing_indexes:
        op.drop_index("ix_attachment_owner_type", table_name="attachment")

    if "owner_id" in existing_columns:
        op.drop_column("attachment", "owner_id")

    if "owner_type" in existing_columns:
        op.drop_column("attachment", "owner_type")
