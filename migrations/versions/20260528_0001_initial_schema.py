"""initial schema

Revision ID: 20260528_0001
Revises: None
Create Date: 2026-05-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20260528_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="用户ID"),
        sa.Column("username", sa.String(length=50), nullable=False, comment="用户名"),
        sa.Column("password_hash", sa.String(length=255), nullable=False, comment="密码哈希"),
        sa.Column("nickname", sa.String(length=50), nullable=True, comment="昵称"),
        sa.Column("email", sa.String(length=255), nullable=True, comment="邮箱"),
        sa.Column("is_super", sa.Boolean(), nullable=False, server_default=sa.text("0"), comment="是否管理员"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1"), comment="是否启用"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="更新时间",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="uk_username"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_comment="用户表",
    )
    op.create_index("idx_created_at", "users", ["created_at"])

    op.create_table(
        "verification_codes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="id"),
        sa.Column("email", sa.String(length=255), nullable=False, comment="邮箱"),
        sa.Column("code", sa.String(length=6), nullable=False, comment="6位验证码"),
        sa.Column("purpose", sa.String(length=50), nullable=False, server_default="password_reset", comment="用途"),
        sa.Column("expires_at", sa.DateTime(), nullable=False, comment="过期时间"),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.text("0"), comment="是否已使用"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_comment="验证码表",
    )
    op.create_index("idx_email", "verification_codes", ["email"])

    op.create_table(
        "ai_chat_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="id"),
        sa.Column("user_id", sa.Integer(), nullable=False, server_default="0", comment="用户ID"),
        sa.Column("model_id", sa.Integer(), nullable=False, server_default="0", comment="模型类型"),
        sa.Column("chat", mysql.JSON(), nullable=False, comment="聊天消息JSON"),
        sa.Column("create_time", sa.DateTime(), nullable=True, comment="创建时间"),
        sa.Column("update_time", sa.DateTime(), nullable=True, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
        mysql_comment="ai聊天记录",
    )
    op.create_index("idx_ai_chat_user_id", "ai_chat_log", ["user_id"])

    op.create_table(
        "user_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="id"),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="用户ID"),
        sa.Column("token", sa.String(length=64), nullable=False, comment="登录Token"),
        sa.Column("expires_at", sa.DateTime(), nullable=False, comment="过期时间"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1"), comment="是否有效"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="更新时间",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uk_token"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_general_ci",
        mysql_comment="用户登录Token",
    )
    op.create_index("idx_user_id", "user_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_user_id", table_name="user_tokens")
    op.drop_table("user_tokens")
    op.drop_index("idx_ai_chat_user_id", table_name="ai_chat_log")
    op.drop_table("ai_chat_log")
    op.drop_index("idx_email", table_name="verification_codes")
    op.drop_table("verification_codes")
    op.drop_index("idx_created_at", table_name="users")
    op.drop_table("users")
