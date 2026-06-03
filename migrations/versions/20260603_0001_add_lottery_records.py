"""add lottery records table

Revision ID: 20260603_0001
Revises: 20261201_0001
Create Date: 2026-06-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260603_0001"
down_revision: Union[str, None] = "20261201_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lottery_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="用户ID"),
        sa.Column("scene_key", sa.String(length=100), nullable=False, comment="抽奖场景标识"),
        sa.Column("request_id", sa.String(length=64), nullable=True, comment="客户端幂等请求ID"),
        sa.Column("draw_index", sa.Integer(), nullable=False, server_default="0", comment="同一请求内抽奖序号"),
        sa.Column("prize_type", sa.String(length=50), nullable=False, server_default="", comment="奖励类型"),
        sa.Column("prize_id", sa.String(length=100), nullable=True, comment="具体奖品ID"),
        sa.Column("amount", sa.String(length=50), nullable=False, server_default="0", comment="奖励金额/数量"),
        sa.Column("props_json", sa.Text(), nullable=True, comment="附加奖品信息JSON"),
        sa.Column("result_json", sa.Text(), nullable=False, comment="完整抽奖结果JSON"),
        sa.Column("grant_status", sa.String(length=20), nullable=False, server_default="pending", comment="发奖状态 pending/success/failed"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_comment="用户抽奖记录表",
    )
    op.create_index("idx_lottery_records_user_scene", "lottery_records", ["user_id", "scene_key"])
    op.create_index("idx_lottery_records_created_at", "lottery_records", ["created_at"])
    op.create_unique_constraint(
        "uk_lottery_record_request_index",
        "lottery_records",
        ["user_id", "scene_key", "request_id", "draw_index"],
    )


def downgrade() -> None:
    op.drop_constraint("uk_lottery_record_request_index", "lottery_records", type_="unique")
    op.drop_index("idx_lottery_records_created_at", table_name="lottery_records")
    op.drop_index("idx_lottery_records_user_scene", table_name="lottery_records")
    op.drop_table("lottery_records")
