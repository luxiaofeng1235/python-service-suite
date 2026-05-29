"""add attachment table

Revision ID: 99b440bc3a16
Revises: 20260528_0003
Create Date: 2026-05-29 03:11:50.199887+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "99b440bc3a16"
down_revision: Union[str, None] = "20260528_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attachment",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="文件ID"),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="上传用户ID"),
        sa.Column("original_name", sa.String(length=255), nullable=False, comment="原始文件名"),
        sa.Column("stored_name", sa.String(length=255), nullable=False, comment="存储文件名"),
        sa.Column("file_path", sa.String(length=500), nullable=False, comment="文件相对路径"),
        sa.Column("file_size", sa.Integer(), nullable=False, comment="文件大小（字节）"),
        sa.Column("mime_type", sa.String(length=100), nullable=False, comment="MIME 类型"),
        sa.Column("file_type", sa.String(length=20), nullable=False, comment="文件分类：image / video / other"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="上传时间"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_comment="附件/文件上传记录表",
    )
    op.create_index(op.f("ix_attachment_user_id"), "attachment", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_attachment_user_id"), table_name="attachment")
    op.drop_table("attachment")
