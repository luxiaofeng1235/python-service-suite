"""
============================================
Business Schema Repair - Missing tables and user login fields
============================================
Create tables omitted by historical migrations without overwriting existing data.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20261111_0001"
down_revision: str | None = "20260616_0001_add_cms_article_tag_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add missing business tables while keeping existing records."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "last_login_ip" not in columns:
        op.add_column("users", sa.Column("last_login_ip", sa.String(45), nullable=True, comment="Last login IP"))
    if "last_login_at" not in columns:
        op.add_column("users", sa.Column("last_login_at", sa.DateTime(), nullable=True, comment="Last login time"))

    if "ai_chat_log" not in tables:
        op.create_table(
            "ai_chat_log",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, comment="Chat ID"),
            sa.Column("user_id", sa.Integer(), nullable=False, server_default="0", comment="User ID"),
            sa.Column("model_id", sa.Integer(), nullable=False, server_default="0", comment="Model type"),
            sa.Column("chat", sa.JSON(), nullable=False, comment="Conversation messages"),
            sa.Column("create_time", sa.DateTime(), nullable=True, comment="Created time"),
            sa.Column("update_time", sa.DateTime(), nullable=True, comment="Updated time"),
            mysql_charset="utf8mb4", mysql_collate="utf8mb4_general_ci",
        )
        op.create_index("idx_ai_chat_user_id", "ai_chat_log", ["user_id"])

    if "ai_to_work" not in tables:
        op.create_table(
            "ai_to_work",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, comment="Task record ID"),
            sa.Column("user_id", sa.Integer(), nullable=False, comment="User ID"),
            sa.Column("task_id", sa.String(255), nullable=True, comment="Upstream task ID"),
            sa.Column("params", sa.JSON(), nullable=False, comment="Generation parameters"),
            sa.Column("work", sa.JSON(none_as_null=True), nullable=True, comment="Generated works"),
            sa.Column("type", mysql.TINYINT(1), nullable=True, server_default="1", comment="1=image 2=video"),
            sa.Column("status", mysql.TINYINT(1), nullable=True, server_default="0", comment="0=generating 1=completed 2=failed 3=deleted"),
            sa.Column("create_time", sa.DateTime(), nullable=True, comment="Created time"),
            sa.Column("update_time", sa.DateTime(), nullable=True, comment="Updated time"),
            sa.UniqueConstraint("task_id", name="task_id"),
            mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_general_ci",
        )

    if "cms_tags" not in tables:
        op.create_table(
            "cms_tags",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, comment="Tag ID"),
            sa.Column("name", sa.String(50), nullable=False, unique=True, comment="Tag name"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="Created time"),
            mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
        )

    if "lottery_configs" not in tables:
        op.create_table(
            "lottery_configs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, comment="Config ID"),
            sa.Column("scene_key", sa.String(100), nullable=False, unique=True, comment="Scene key"),
            sa.Column("name", sa.String(100), nullable=False, server_default="", comment="Scene name"),
            sa.Column("config_json", sa.Text(), nullable=False, comment="Lottery configuration JSON"),
            sa.Column("status", mysql.TINYINT(1), nullable=False, server_default="1", comment="1=enabled 0=disabled"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="Created time"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="Updated time"),
            mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
        )


def downgrade() -> None:
    """Prevent removal of tables that might predate this repair."""
    raise RuntimeError("该迁移兼容已有业务表，不支持自动降级；请从备份恢复")
